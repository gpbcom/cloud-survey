from __future__ import annotations

# Standard Library Imports.
from datetime import date, timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.companies.financials.flow_quarters import FlowQuarters
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import FinancialGranularity, FinancialMetric, FinancialNature, FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.companies.values.financial_value import FinancialValue

type Duration = Tuple[date, date]
type PeriodKey = Tuple[FinancialMetric, FinancialGranularity, date]
type Rank = Tuple[int, int, int]
type ConceptRank = Tuple[FinancialMetric, FinancialNature, int]
type SumKey = Tuple[FinancialMetric, Optional[str], Optional[date], date, str]


class FinancialResolver:
    """Turn the facts of a company's sources into one statement line per metric, period and source.

    Attributes:
        DERIVED (ClassVar[str]): The concept prefix of a quarter derived from year-to-date figures.
        SCHEDULE (ClassVar[str]): The concept prefix of a tag of the financial data schedules.
        PERIOD_MONTHS (ClassVar[Dict[str, int]]): The months of each period type of a schedule (`9M`: nine).
        concepts (FinancialConcepts): How the statement lines are read (the rank of each concept, the nature of each
            line).
        flows (FlowQuarters): Derives the quarters of the year-to-date figures.
        logger (Logger): The resolver logger.

    Notes:
        - XBRL: a period is filed again by every later filing comparing with it. The latest filing of a period wins
          (a restatement replaces the first figure). The company's current filer wins over its former ones, which
          only fill the periods before the current filer's first one (HP Inc. is not completed by Hewlett Packard
          Enterprise, filed from 2015). A concept wins over the later ones of its line (a later one only fills the
          periods the first lacks), a filed quarter over a derived one.
        - A balance is read at its date (`instant`), a flow per quarter and per fiscal year, a per-share figure as
          filed (never derived: the quarters of an earnings per share do not add up).
        - Google Finance states each period once: its figures are kept as they are.
        - The SEC financial data schedules (1993 to 2001) are resolved like the XBRL facts, apart from them (their
          own source): the latest filing of a period wins, the quarters of the year-to-date schedules are derived.
          A line summing several tags (the equity: common stock, other equity, preferred stock) adds the tags one
          schedule column states. A flow without a stated start starts where its period type says (`9M`: nine
          months before its end).
    """

    DERIVED: ClassVar[str] = "derived:"
    SCHEDULE: ClassVar[str] = "fds:"
    PERIOD_MONTHS: ClassVar[Dict[str, int]] = {"FY": 12, "3M": 3, "6M": 6, "9M": 9}

    def __init__(self, concepts: FinancialConcepts, logger: Optional[Logger] = None) -> None:
        """Initialize the resolver.

        Args:
            concepts (FinancialConcepts): How the statement lines are read.
            logger (Optional[Logger]): The resolver logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.concepts = concepts
        self.flows = FlowQuarters(logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _latest(
        self, facts: Sequence[FinancialFact]
    ) -> Dict[Tuple[str, Optional[str], Optional[date], date], FinancialFact]:
        """Keep the latest filing of each period of each concept and filer.

        Args:
            facts (Sequence[FinancialFact]): The XBRL facts.

        Returns:
            Dict[Tuple[str, Optional[str], Optional[date], date], FinancialFact]: The latest fact, by concept, filer,
                first day and last day.
        """
        latest: Dict[Tuple[str, Optional[str], Optional[date], date], FinancialFact] = {}
        for fact in facts:
            key = (fact.concept, fact.filer, fact.start, fact.end)
            kept = latest.get(key)
            if kept is None or (fact.filed or date.min) >= (kept.filed or date.min):
                latest[key] = fact
        return latest

    def _xbrl_ranks(self) -> Dict[str, ConceptRank]:
        """Get the statement line, nature and rank of each XBRL concept.

        Returns:
            Dict[str, ConceptRank]: The line, its nature and the concept's rank among the line's concepts.
        """
        return {
            name: (concept.metric, concept.nature, rank) for name, (concept, rank) in self.concepts.by_concept().items()
        }

    def _schedule_ranks(self) -> Dict[str, ConceptRank]:
        """Get the statement line, nature and rank of each tag of the financial data schedules.

        Returns:
            Dict[str, ConceptRank]: The line, its nature and the tag's rank, by `fds:TAG` (a summed line also by
                `fds:<line>`).
        """
        ranks: Dict[str, ConceptRank] = {}
        for tag in self.concepts.fds.tags:
            nature = self.concepts.nature(tag.metric)
            if nature is None:
                self.logger.warning("Schedule tag %s maps to %s, a line without nature: left out.", tag.tag, tag.metric)
                continue
            key = f"{self.SCHEDULE}{tag.metric.value}" if tag.sum else f"{self.SCHEDULE}{tag.tag}"
            ranks[key] = (tag.metric, nature, tag.rank)
        return ranks

    def _schedule_start(self, fact: FinancialFact) -> FinancialFact:
        """Give a schedule flow without a stated start the start its period type implies.

        Args:
            fact (FinancialFact): A schedule fact.

        Returns:
            FinancialFact: The fact, with a start when it is a flow whose period type is known.
        """
        months = self.PERIOD_MONTHS.get(fact.fiscal_period or "")
        if fact.start is not None or months is None or self.concepts.nature(fact.metric) is FinancialNature.BALANCE:
            return fact
        year, month = fact.end.year, fact.end.month - months
        while month < 1:
            year, month = year - 1, month + 12
        anchor = date(year, month, min(fact.end.day, 28))
        return fact.model_copy(update={"start": anchor + timedelta(days=1)})

    def _summed(self, facts: Sequence[FinancialFact]) -> List[FinancialFact]:
        """Add the tags of a summed line stated by one schedule column (the equity's three tags).

        Args:
            facts (Sequence[FinancialFact]): The schedule facts.

        Returns:
            List[FinancialFact]: The facts, the tags of a summed line replaced by their sum (`fds:<line>`).
        """
        summed_tags = {f"{self.SCHEDULE}{tag.tag}" for tag in self.concepts.fds.tags if tag.sum}
        kept: List[FinancialFact] = []
        sums: Dict[SumKey, FinancialFact] = {}
        for fact in facts:
            if fact.concept not in summed_tags:
                kept.append(fact)
                continue
            key = (fact.metric, fact.filer, fact.start, fact.end, fact.source_url)
            total = sums.get(key)
            concept = f"{self.SCHEDULE}{fact.metric.value}"
            value = fact.value + (total.value if total else 0.0)
            sums[key] = fact.model_copy(update={"concept": concept, "value": value})
        return kept + list(sums.values())

    def _value(
        self, fact: FinancialFact, granularity: FinancialGranularity, value: float, concept: str
    ) -> FinancialValue:
        """Build the stored line of a fact.

        Args:
            fact (FinancialFact): The fact (or the latest fact of a derived quarter).
            granularity (FinancialGranularity): The period.
            value (float): The figure.
            concept (str): The concept it was read from.

        Returns:
            FinancialValue: The line.
        """
        return FinancialValue(
            company=fact.company,
            metric=fact.metric,
            period_end=fact.end,
            granularity=granularity,
            source=fact.source,
            value=value,
            currency=fact.currency,
            concept=concept,
            form=fact.form,
            fiscal_year=fact.fiscal_year if fact.source is FinancialSource.GOOGLE_FINANCE else None,
            fiscal_period=fact.fiscal_period if fact.source is FinancialSource.GOOGLE_FINANCE else None,
            filed=fact.filed,
            source_url=fact.source_url,
        )

    def _candidates(
        self, facts: Sequence[FinancialFact], filers: Dict[str, int], ranks: Dict[str, ConceptRank]
    ) -> List[Tuple[PeriodKey, Rank, FinancialValue]]:
        """Get every candidate line of filed facts (XBRL, or financial data schedules), ranked.

        Args:
            facts (Sequence[FinancialFact]): The filed facts of a company, one source.
            filers (Dict[str, int]): The rank of each filer of the company (0 for the current one).
            ranks (Dict[str, ConceptRank]): The line, nature and rank of each concept of the source.

        Returns:
            List[Tuple[PeriodKey, Rank, FinancialValue]]: Each candidate line, its key and its rank (lower wins).
        """
        latest = self._latest(facts)
        groups: Dict[Tuple[str, Optional[str]], Dict[Duration, FinancialFact]] = {}
        candidates: List[Tuple[PeriodKey, Rank, FinancialValue]] = []
        for (concept, filer, start, end), fact in latest.items():
            definition = ranks.get(concept)
            if definition is None:
                continue
            rank = (filers.get(filer or "", len(filers)), definition[2], 0)
            if start is None or definition[1] is FinancialNature.BALANCE:
                line = self._value(fact, FinancialGranularity.INSTANT, fact.value, concept)
                candidates.append(((fact.metric, FinancialGranularity.INSTANT, end), rank, line))
                continue
            groups.setdefault((concept, filer), {})[(start, end)] = fact
        for (concept, filer), periods in groups.items():
            definition = ranks[concept]
            base = (filers.get(filer or "", len(filers)), definition[2])
            durations = {period: fact.value for period, fact in periods.items()}
            by_end = {end: fact for (_, end), fact in periods.items()}
            for end, amount in self.flows.years(durations).items():
                key = (definition[0], FinancialGranularity.YEAR, end)
                candidates.append(
                    (key, (*base, 0), self._value(by_end[end], FinancialGranularity.YEAR, amount, concept))
                )
            filed, derived = self.flows.quarters(durations)
            if definition[1] is FinancialNature.PER_SHARE:
                derived = {}
            for end, amount in filed.items():
                key = (definition[0], FinancialGranularity.QUARTER, end)
                candidates.append(
                    (key, (*base, 0), self._value(by_end[end], FinancialGranularity.QUARTER, amount, concept))
                )
            for end, amount in derived.items():
                key = (definition[0], FinancialGranularity.QUARTER, end)
                line = self._value(by_end[end], FinancialGranularity.QUARTER, amount, f"{self.DERIVED}{concept}")
                candidates.append((key, (*base, 1), line))
        return candidates

    def _best(self, candidates: List[Tuple[PeriodKey, Rank, FinancialValue]]) -> List[FinancialValue]:
        """Keep the best candidate of each period: the current filer's, then the preferred concept's.

        Args:
            candidates (List[Tuple[PeriodKey, Rank, FinancialValue]]): The candidate lines of one source, ranked.

        Returns:
            List[FinancialValue]: The kept line of each period (a former filer only fills the periods before the
                first one of a later filer).
        """
        first_ends: Dict[int, date] = {}
        for key, rank, _ in candidates:
            first_ends[rank[0]] = min(first_ends.get(rank[0], key[2]), key[2])
        best: Dict[PeriodKey, Tuple[Rank, FinancialValue]] = {}
        for key, rank, value in candidates:
            earlier = [end for filer, end in first_ends.items() if filer < rank[0]]
            if earlier and key[2] >= min(earlier):
                continue
            kept = best.get(key)
            if kept is None or rank < kept[0]:
                best[key] = (rank, value)
        return [value for _, value in best.values()]

    ############################
    # Publicly Exposed Methods #
    ############################

    def resolve(self, entry: CompanyEntry, facts: Sequence[FinancialFact]) -> List[FinancialValue]:
        """Resolve the facts of a company into its statement lines, one per metric, period and source.

        Args:
            entry (CompanyEntry): The company (the order of its filers).
            facts (Sequence[FinancialFact]): Its facts, from any source.

        Returns:
            List[FinancialValue]: The lines, by metric, granularity and period.
        """
        filers = {cik: rank for rank, cik in enumerate(entry.sec_ciks)}
        schedules = [self._schedule_start(fact) for fact in facts if fact.source is FinancialSource.EDGAR_FDS]
        sources = {
            FinancialSource.EDGAR: (
                [fact for fact in facts if fact.source is FinancialSource.EDGAR],
                self._xbrl_ranks(),
            ),
            FinancialSource.EDGAR_FDS: (self._summed(schedules), self._schedule_ranks()),
        }
        values: List[FinancialValue] = []
        filed = 0
        for source_facts, ranks in sources.values():
            best = self._best(self._candidates(source_facts, filers, ranks))
            filed += len(best)
            values += best
        google: Dict[PeriodKey, FinancialValue] = {}
        for fact in facts:
            if fact.source is FinancialSource.GOOGLE_FINANCE and fact.granularity is not None:
                google[(fact.metric, fact.granularity, fact.end)] = self._value(
                    fact, fact.granularity, fact.value, fact.concept
                )
        values += list(google.values())
        values.sort(
            key=lambda value: (value.source.value, value.metric.value, value.granularity.value, value.period_end)
        )
        self.logger.info(
            "%s: %d facts resolved into %d statement lines (%d SEC, %d Google).",
            entry.key,
            len(facts),
            len(values),
            filed,
            len(google),
        )
        return values
