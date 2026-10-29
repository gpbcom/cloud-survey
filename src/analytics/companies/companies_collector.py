from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Pattern, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import BaseModel, JsonValue, ValidationError

# First Party Imports.
from analytics.companies.checks.figure_check_collector import FigureCheckCollector
from analytics.companies.exception import CompaniesCollectorError
from analytics.companies.financials.financial_resolver import FinancialResolver
from analytics.companies.financials.reported_lines import ReportedLines
from analytics.companies.health.altman_score import AltmanScore
from analytics.companies.health.growth_indicators import GrowthIndicators
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.health.piotroski_score import PiotroskiScore
from analytics.companies.health.private_proxies import PrivateProxies
from analytics.companies.identities.identity_collector import IdentityCollector
from analytics.companies.indicators.currency_rates import CurrencyRates
from analytics.companies.indicators.financial_book import FinancialBook
from analytics.companies.indicators.financial_indicators import FinancialIndicators
from analytics.companies.indicators.market_value import MarketValue
from analytics.companies.indicators.research_indicators import ResearchIndicators
from models.companies.checks.document_numbers import DocumentNumbers
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFactKind, CompanyFeed, CompanyIndicator, FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.companies.figures.reported_figures import ReportedFigures
from models.companies.identities.identity_candidate import IdentityCandidate
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.companies.values.indicator_value import IndicatorValue
from models.markets.markets_catalog import MarketsCatalog
from storage.storage import Storage


class CompaniesCollector:
    """Measure and write the facts of the companies crawls, then derive the indicator series.

    Attributes:
        KIND_KEY (ClassVar[str]): The item key naming the kind of fact.
        MODELS (ClassVar[Dict[CompanyFactKind, type[BaseModel]]]): The model of each kind of fact.
        FINANCIAL_FEEDS (ClassVar[Tuple[CompanyFeed, ...]]): The feeds of the statements.
        REPLACED (ClassVar[Tuple[FinancialSource, ...]]): The sources whose lines of a company a crawl replaces whole.
        PATENT_FEEDS (ClassVar[Tuple[CompanyFeed, ...]]): The feeds of the patents.
        FINANCIAL_INDICATORS (ClassVar[Tuple[CompanyIndicator, ...]]): The indicators derived from the statements and
            the prices.
        companies (CompaniesCatalog): Where each company is found (its filers, its homonym patterns).
        concepts (FinancialConcepts): How the statement lines are read.
        markets (MarketsCatalog): The listings.
        storage (Storage): The open storage.
        scope (List[str]): The companies crawled, every one when empty.
        resolver (FinancialResolver): Resolves the facts of a company into its statement lines.
        research (ResearchIndicators): Builds the patents and papers series.
        reported (ReportedLines): Turns the figures researched by hand into statement lines.
        pending (Dict[str, List[FinancialFact]]): The statement facts of each company, resolved after the crawls.
        crawled (Set[str]): The companies whose statements were written in this run.
        excluded (Dict[str, List[Pattern[str]]]): The homonym patterns of each company.
        rejected (int): The patents left out as homonyms.
        logger (Logger): The collector logger.

    Notes:
        - The statement facts of a company (one crawl request per filer or quote page) are kept until the crawls are
          over, then resolved together: a filer's year-to-date facts and the precedence of its filers need them all.
        - The SEC lines of a company are replaced whole (a `companyfacts` document holds the filer's whole history,
          the data schedules crawl reads every schedule filed), the Google Finance ones accumulate (the page only
          shows its last years). The researched figures of a company are replaced whole from their catalogue.
        - The patents of a homonym (an assignee matching an exclusion pattern of the company) are left out.
        - `finish` derives the indicators of the companies read from everything stored (both statement sources,
          the prices, the exchange rates, the patents, the papers), and replaces their series.
    """

    KIND_KEY: ClassVar[str] = "kind"
    MODELS: ClassVar[Dict[CompanyFactKind, type[BaseModel]]] = {
        CompanyFactKind.FINANCIAL: FinancialFact,
        CompanyFactKind.PATENT: PatentRecord,
        CompanyFactKind.PATENT_DETAIL: PatentDetail,
        CompanyFactKind.PATENT_WINDOW: PatentWindow,
        CompanyFactKind.PAPER: PaperRecord,
        CompanyFactKind.RESEARCHER: ResearcherRecord,
        CompanyFactKind.PAPER_COUNT: PaperYearCount,
        CompanyFactKind.IDENTITY: IdentityCandidate,
        CompanyFactKind.DOCUMENT_NUMBERS: DocumentNumbers,
    }
    FINANCIAL_FEEDS: ClassVar[Tuple[CompanyFeed, ...]] = (
        CompanyFeed.EDGAR,
        CompanyFeed.GOOGLE_FINANCE,
        CompanyFeed.EDGAR_SCHEDULES,
        CompanyFeed.REPORTED,
    )
    REPLACED: ClassVar[Tuple[FinancialSource, ...]] = (FinancialSource.EDGAR, FinancialSource.EDGAR_FDS)
    PATENT_FEEDS: ClassVar[Tuple[CompanyFeed, ...]] = (CompanyFeed.GOOGLE_PATENTS, CompanyFeed.GOOGLE_PATENT_PAGES)
    FINANCIAL_INDICATORS: ClassVar[Tuple[CompanyIndicator, ...]] = (
        CompanyIndicator.REVENUE,
        CompanyIndicator.NET_INCOME,
        CompanyIndicator.OPERATING_INCOME,
        CompanyIndicator.EBITDA,
        CompanyIndicator.TOTAL_ASSETS,
        CompanyIndicator.TOTAL_EQUITY,
        CompanyIndicator.MARKET_CAP,
        CompanyIndicator.ENTERPRISE_VALUE,
        CompanyIndicator.GROSS_MARGIN,
        CompanyIndicator.OPERATING_MARGIN,
        CompanyIndicator.NET_MARGIN,
        CompanyIndicator.ROE,
        CompanyIndicator.ROA,
        CompanyIndicator.ROIC,
        CompanyIndicator.FREE_CASH_FLOW,
        CompanyIndicator.CASH,
        CompanyIndicator.TOTAL_DEBT,
        CompanyIndicator.NET_DEBT,
        CompanyIndicator.DEBT_TO_EQUITY,
        CompanyIndicator.NET_DEBT_TO_EBITDA,
        CompanyIndicator.CURRENT_RATIO,
        CompanyIndicator.QUICK_RATIO,
        CompanyIndicator.RD_EXPENSE,
        CompanyIndicator.RD_INTENSITY,
        CompanyIndicator.CAPITALISED_DEVELOPMENT,
        CompanyIndicator.RD_RETURN,
        CompanyIndicator.REVENUE_GROWTH,
        CompanyIndicator.NET_INCOME_GROWTH,
        CompanyIndicator.RD_GROWTH,
        CompanyIndicator.INTEREST_COVERAGE,
        CompanyIndicator.CASH_CONVERSION,
        CompanyIndicator.WORKING_CAPITAL,
        CompanyIndicator.PAYOUT_RATIO,
        CompanyIndicator.ALTMAN_Z,
        CompanyIndicator.ALTMAN_Z_DOUBLE_PRIME,
        CompanyIndicator.PIOTROSKI_F,
        CompanyIndicator.EMPLOYEES,
        CompanyIndicator.FUNDING_RAISED,
        CompanyIndicator.FUNDING_TOTAL,
        CompanyIndicator.VALUATION,
        CompanyIndicator.REVENUE_RUN_RATE,
    )

    def __init__(
        self,
        companies: CompaniesCatalog,
        concepts: FinancialConcepts,
        markets: MarketsCatalog,
        storage: Storage,
        scope: Optional[Sequence[str]] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the collector.

        Args:
            companies (CompaniesCatalog): Where each company is found.
            concepts (FinancialConcepts): How the statement lines are read.
            markets (MarketsCatalog): The listings.
            storage (Storage): The open storage.
            scope (Optional[Sequence[str]]): The companies crawled, every one when empty.
            logger (Optional[Logger]): The collector logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.companies = companies
        self.concepts = concepts
        self.markets = markets
        self.storage = storage
        self.scope = list(scope or [])
        self.resolver = FinancialResolver(concepts, logger=self.logger)
        self.research = ResearchIndicators(logger=self.logger)
        self.reported = ReportedLines(concepts, logger=self.logger)
        self.identities = IdentityCollector(storage, logger=self.logger)
        self.checks = FigureCheckCollector(storage, logger=self.logger)
        self.pending: Dict[str, List[FinancialFact]] = {}
        self.crawled: Set[str] = set()
        self.excluded: Dict[str, List[Pattern[str]]] = {
            entry.key: [re.compile(pattern, re.IGNORECASE) for pattern in entry.patents.exclude]
            for entry in companies.companies
            if entry.patents is not None
        }
        self.rejected = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _facts[Model: BaseModel](self, model: type[Model], items: Sequence[Dict[str, JsonValue]]) -> List[Model]:
        """Validate the items of a kind (an invalid one is logged and left out).

        Args:
            model (type[Model]): The model of the kind.
            items (Sequence[Dict[str, JsonValue]]): The items, without their kind key.

        Returns:
            List[Model]: The facts.
        """
        facts: List[Model] = []
        for item in items:
            try:
                facts.append(model.model_validate(item))
            except ValidationError as e:
                self.logger.warning("Invalid %s fact left out: %s", model.__name__, e.errors()[0]["msg"])
        return facts

    def _by_kind(self, items: Sequence[Dict[str, JsonValue]]) -> Dict[CompanyFactKind, List[Dict[str, JsonValue]]]:
        """Sort the items of a batch by kind.

        Args:
            items (Sequence[Dict[str, JsonValue]]): The items.

        Returns:
            Dict[CompanyFactKind, List[Dict[str, JsonValue]]]: The items of each kind, without their kind key.
        """
        kinds: Dict[CompanyFactKind, List[Dict[str, JsonValue]]] = {}
        for item in items:
            raw = item.get(self.KIND_KEY)
            if not isinstance(raw, str) or raw not in self.MODELS:
                self.logger.warning("An item without a known kind is left out (%r).", raw)
                continue
            kinds.setdefault(CompanyFactKind(raw), []).append(
                {key: value for key, value in item.items() if key != self.KIND_KEY}
            )
        return kinds

    def _is_homonym(self, record: PatentRecord) -> bool:
        """Tell whether a publication belongs to a homonym of its company.

        Args:
            record (PatentRecord): The publication.

        Returns:
            bool: Whether its assignee matches an exclusion pattern of the company.
        """
        assignee = record.assignee or ""
        return any(pattern.search(assignee) for pattern in self.excluded.get(record.company, []))

    async def _flush(self, company: str, facts: List[FinancialFact]) -> int:
        """Resolve and write the statement facts of a company.

        Args:
            company (str): The company.
            facts (List[FinancialFact]): Its facts, every source.

        Returns:
            int: The statement lines written.

        Raises:
            StorageWriteError: If the lines cannot be written.
        """
        entry = self.companies.entry(company)
        if entry is None:
            self.logger.warning("Statement facts of %s, not in the companies catalogue, left out.", company)
            return 0
        self.crawled.add(company)
        values = self.resolver.resolve(entry, facts)
        written = 0
        for source in self.REPLACED:
            lines = [value for value in values if value.source is source]
            written += await self.storage.financials.replace(company, source, lines) if lines else 0
        rest = [value for value in values if value.source not in self.REPLACED]
        return written + await self.storage.financials.upsert(rest)

    def _financials(self, facts: Sequence[FinancialFact]) -> int:
        """Keep the statement facts of a batch, by company, until the crawls are over.

        Args:
            facts (Sequence[FinancialFact]): The facts.

        Returns:
            int: The statement lines written, none yet.
        """
        for fact in facts:
            self.pending.setdefault(fact.company, []).append(fact)
        self.logger.debug("%d statement facts kept for %d companies.", len(facts), len(self.pending))
        return 0

    async def _financial_indicators(self) -> int:
        """Derive the financial indicators of the companies read, from both statement sources and the prices.

        Returns:
            int: The points written.

        Raises:
            StorageReadError: If the stored data cannot be read.
            StorageWriteError: If the points cannot be written.
        """
        companies = sorted(self.crawled) if not self.scope else [key for key in self.scope if self.companies.entry(key)]
        if not companies:
            self.logger.warning("No company statement was written: the financial indicators are kept as stored.")
            return 0
        rates = CurrencyRates(await self.storage.fx.list(), logger=self.logger)
        calculator = FinancialIndicators(rates, logger=self.logger)
        market = MarketValue(rates, logger=self.logger)
        builder = IndicatorPoints(rates, logger=self.logger)
        growth = GrowthIndicators(builder, logger=self.logger)
        altman = AltmanScore(rates, builder, logger=self.logger)
        piotroski = PiotroskiScore(builder, logger=self.logger)
        proxies = PrivateProxies(builder, logger=self.logger)
        values = await self.storage.financials.list(companies)
        points: List[IndicatorValue] = []
        for company in companies:
            entry = self.companies.entry(company)
            if entry is None:
                continue
            book = FinancialBook(
                [value for value in values if value.company == company], self.concepts, logger=self.logger
            )
            points += calculator.compute(company, book, entry.statements)
            listings = self.markets.listings_of(company)
            listing = (
                self.markets.listing(entry.market_cap.listing)
                if entry.market_cap
                else (listings[0] if listings else None)
            )
            valued: List[IndicatorValue] = []
            if listing is not None:
                prices = await self.storage.stocks.list([listing.symbol])
                valued = market.compute(entry, listing, prices, book)
            points += valued
            points += growth.compute(company, book)
            points += altman.compute(company, book, valued, entry.statements)
            points += piotroski.compute(company, book, entry.statements)
            points += proxies.compute(company, book, self.markets.valuations)
        return await self.storage.indicators.replace(companies, self.FINANCIAL_INDICATORS, points)

    async def _patent_indicators(self) -> int:
        """Derive the patents series and the inventor and assignee profiles.

        Returns:
            int: The points written.

        Raises:
            StorageReadError: If the patents cannot be read.
            StorageWriteError: If the profiles or the points cannot be written.
        """
        await self.storage.patent_profiles.rebuild()
        figures = await self.storage.patents.yearly(self.scope)
        points = self.research.from_years(figures)
        companies = self.scope or sorted({key[0] for key in figures})
        return await self.storage.indicators.replace(companies, ResearchIndicators.PATENTS, points)

    async def _paper_indicators(self) -> int:
        """Derive the papers series from the stored papers (the yearly counts are written as they come).

        Returns:
            int: The points written.

        Raises:
            StorageReadError: If the papers cannot be read.
            StorageWriteError: If the points cannot be written.
        """
        figures = await self.storage.papers.yearly(self.scope)
        points = self.research.from_years(figures)
        companies = self.scope or sorted({key[0] for key in figures})
        return await self.storage.indicators.replace(companies, ResearchIndicators.PAPERS, points)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def write(self, feed: CompanyFeed, items: List[Dict[str, JsonValue]]) -> int:
        """Measure and write a batch of crawled facts (the sink of a companies crawl).

        Args:
            feed (CompanyFeed): The source of the batch.
            items (List[Dict[str, JsonValue]]): The facts, each naming its kind.

        Returns:
            int: The rows written.

        Raises:
            StorageWriteError: If the rows cannot be written.
        """
        written = 0
        for kind, raw in self._by_kind(items).items():
            match kind:
                case CompanyFactKind.FINANCIAL:
                    written += self._financials(self._facts(FinancialFact, raw))
                case CompanyFactKind.PATENT:
                    records = self._facts(PatentRecord, raw)
                    kept = [record for record in records if not self._is_homonym(record)]
                    self.rejected += len(records) - len(kept)
                    written += await self.storage.patents.upsert_records(kept)
                case CompanyFactKind.PATENT_WINDOW:
                    written += await self.storage.patents.upsert_windows(self._facts(PatentWindow, raw))
                case CompanyFactKind.PATENT_DETAIL:
                    written += await self.storage.patents.upsert_details(self._facts(PatentDetail, raw))
                case CompanyFactKind.PAPER:
                    written += await self.storage.papers.upsert_papers(self._facts(PaperRecord, raw))
                case CompanyFactKind.RESEARCHER:
                    written += await self.storage.papers.upsert_researchers(self._facts(ResearcherRecord, raw))
                case CompanyFactKind.PAPER_COUNT:
                    points = self.research.from_counts(self._facts(PaperYearCount, raw))
                    written += await self.storage.indicators.replace([], [CompanyIndicator.PAPERS], points)
                case CompanyFactKind.IDENTITY:
                    written += await self.identities.write(self._facts(IdentityCandidate, raw))
                case CompanyFactKind.DOCUMENT_NUMBERS:
                    written += await self.checks.write(self._facts(DocumentNumbers, raw))
        self.logger.debug("%s batch of %d facts: %d rows written.", feed.value, len(items), written)
        return written

    async def write_reported(self, figures: ReportedFigures) -> int:
        """Write the figures researched by hand of the companies read, replacing their stored ones.

        Args:
            figures (ReportedFigures): The researched figures.

        Returns:
            int: The lines written.

        Raises:
            CompaniesCollectorError: If the figures research no company (an empty catalogue would delete the stored
                figures of every company).
            StorageWriteError: If the lines cannot be written.
        """
        if not figures.companies:
            self.logger.error("The researched figures hold no company: the stored figures are left as they are.")
            raise CompaniesCollectorError("the researched figures hold no company (seed the curated bundle first).")
        keys = self.scope or [entry.key for entry in self.companies.companies]
        written = 0
        for key in keys:
            entry = figures.of(key)
            lines = self.reported.lines(entry) if entry is not None else []
            if lines:
                written += await self.storage.financials.replace(key, FinancialSource.REPORTED, lines)
                self.crawled.add(key)
            elif await self.storage.financials.delete_source(key, FinancialSource.REPORTED):
                self.crawled.add(key)
        if not written:
            self.logger.warning("No researched figure written for %d companies.", len(keys))
        self.logger.info("%d researched lines written for %d companies.", written, len(keys))
        return written

    async def finish(self, feeds: Sequence[CompanyFeed]) -> int:
        """Write the companies' statements, then derive the indicators of the sources crawled.

        Args:
            feeds (Sequence[CompanyFeed]): The sources crawled in this run.

        Returns:
            int: The rows written.

        Raises:
            StorageReadError: If the stored data cannot be read.
            StorageWriteError: If the rows cannot be written.
        """
        written = 0
        for company, facts in sorted(self.pending.items()):
            written += await self._flush(company, facts)
        self.pending = {}
        if any(feed in self.FINANCIAL_FEEDS for feed in feeds):
            written += await self._financial_indicators()
        if any(feed in self.PATENT_FEEDS for feed in feeds):
            if self.rejected:
                self.logger.info(
                    "%d patents of homonyms left out (exclusion patterns of the catalogue).", self.rejected
                )
            written += await self._patent_indicators()
        if CompanyFeed.OPENALEX in feeds:
            written += await self._paper_indicators()
        self.logger.info("Companies run finished: %d rows written by the derivations.", written)
        return written
