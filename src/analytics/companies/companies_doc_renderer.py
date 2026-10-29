from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.enums import CompanyIndicator, FinancialGranularity
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog

type CoverageKey = Tuple[str, str, str]
type Span = Tuple[date, date, int]


class CompaniesDocRenderer:
    """Print the generated blocks of the companies guide: the catalogue and the coverage of the stored series.

    Attributes:
        START (ClassVar[str]): The opening marker of a generated block, formatted with its name.
        END (ClassVar[str]): The closing marker of a generated block, formatted with its name.
        CATALOGUE (ClassVar[str]): The name of the catalogue block.
        COVERAGE (ClassVar[str]): The name of the coverage block.
        COLUMNS (ClassVar[Tuple[Tuple[CompanyIndicator, FinancialGranularity, str], ...]]): The series of the coverage
            table, with their column names.
        logger (Logger): The renderer logger.
    """

    START: ClassVar[str] = "<!-- companies:{name}:start -->"
    END: ClassVar[str] = "<!-- companies:{name}:end -->"
    CATALOGUE: ClassVar[str] = "catalogue"
    COVERAGE: ClassVar[str] = "coverage"
    COLUMNS: ClassVar[Tuple[Tuple[CompanyIndicator, FinancialGranularity, str], ...]] = (
        (CompanyIndicator.REVENUE, FinancialGranularity.QUARTER, "Revenue (quarters)"),
        (CompanyIndicator.REVENUE, FinancialGranularity.YEAR, "Revenue (years)"),
        (CompanyIndicator.RD_INTENSITY, FinancialGranularity.YEAR, "R&D intensity (years)"),
        (CompanyIndicator.ROE, FinancialGranularity.TTM, "ROE (TTM)"),
        (CompanyIndicator.ALTMAN_Z_DOUBLE_PRIME, FinancialGranularity.YEAR, "Altman Z'' (years)"),
        (CompanyIndicator.PIOTROSKI_F, FinancialGranularity.YEAR, "Piotroski F (years)"),
        (CompanyIndicator.MARKET_CAP, FinancialGranularity.WEEK, "Market cap (weeks)"),
        (CompanyIndicator.PATENT_FILINGS, FinancialGranularity.YEAR, "Patent filings"),
        (CompanyIndicator.PATENT_CITATIONS, FinancialGranularity.YEAR, "Patent citations"),
        (CompanyIndicator.PAPERS, FinancialGranularity.YEAR, "Papers"),
    )

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            logger (Optional[Logger]): The renderer logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _cell(self, text: str) -> str:
        """Escape a table cell.

        Args:
            text (str): The text.

        Returns:
            str: The text, its pipes escaped.
        """
        return text.replace("|", "\\|")

    def _table(self, header: Sequence[str], rows: Sequence[Sequence[str]]) -> List[str]:
        """Print a Markdown table.

        Args:
            header (Sequence[str]): The column names.
            rows (Sequence[Sequence[str]]): The rows.

        Returns:
            List[str]: The lines of the table.
        """
        lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        lines += ["| " + " | ".join(self._cell(cell) for cell in row) + " |" for row in rows]
        return lines

    def _span(self, span: Optional[Span]) -> str:
        """Print the span of a series.

        Args:
            span (Optional[Span]): Its first and last period ends and its points.

        Returns:
            str: `first to last (points)`, a dash when nothing is stored.
        """
        if span is None:
            return "-"
        first, last, points = span
        return f"{first.isoformat()} to {last.isoformat()} ({points})"

    ############################
    # Publicly Exposed Methods #
    ############################

    def catalogue(self, catalog: CompaniesCatalog, chronology: Chronology, markets: MarketsCatalog) -> str:
        """Print where each company's statements, patents and papers are read.

        Args:
            catalog (CompaniesCatalog): The companies catalogue.
            chronology (Chronology): The chronology naming the companies.
            markets (MarketsCatalog): The listings.

        Returns:
            str: The block: one row per company.
        """
        labels = {company.key: company.label for company in chronology.companies}
        rows: List[List[str]] = []
        for entry in catalog.companies:
            listings = markets.listings_of(entry.key)
            listing = entry.market_cap.listing if entry.market_cap else (listings[0].symbol if listings else "-")
            patents = entry.patents
            rows.append(
                [
                    labels.get(entry.key, entry.key),
                    f"`{entry.key}`",
                    str(len(entry.sec_ciks)) if entry.sec_ciks else "-",
                    listing,
                    ", ".join(patents.assignees) if patents else "-",
                    patents.since.isoformat() if patents else "-",
                    ", ".join(entry.openalex.institutions) or "-",
                ]
            )
        header = ["Company", "Key", "SEC filers", "Valued listing", "Patent assignee searches", "Since", "OpenAlex"]
        lines = self._table(header, rows)
        lines.append("")
        lines.append(
            f"{len(catalog.companies)} companies: {sum(1 for entry in catalog.companies if entry.sec_ciks)} with SEC "
            f"filers, {sum(1 for entry in catalog.companies if markets.listings_of(entry.key))} listed, "
            f"{sum(1 for entry in catalog.companies if entry.patents)} with patent searches, "
            f"{sum(1 for entry in catalog.companies if entry.openalex.institutions)} with OpenAlex institutions."
        )
        self.logger.debug("Companies catalogue block printed: %d rows.", len(rows))
        return "\n".join(lines)

    def coverage(self, catalog: CompaniesCatalog, spans: Dict[CoverageKey, Span], today: date) -> str:
        """Print the span of the main stored series of each company.

        Args:
            catalog (CompaniesCatalog): The companies catalogue.
            spans (Dict[CoverageKey, Span]): The stored span of each series, by company, indicator and granularity.
            today (date): The day of the report.

        Returns:
            str: The block: one row per company, one column per series.
        """
        rows = [
            [f"`{entry.key}`"]
            + [
                self._span(spans.get((entry.key, indicator.value, granularity.value)))
                for indicator, granularity, _ in self.COLUMNS
            ]
            for entry in catalog.companies
        ]
        lines = [f"Stored on {today.isoformat()}: first period end to last period end (points).", ""]
        lines += self._table(["Company", *(name for _, _, name in self.COLUMNS)], rows)
        covered = sum(1 for row in rows if any(cell != "-" for cell in row[1:]))
        self.logger.info("Companies coverage block printed: %d of %d companies with stored series.", covered, len(rows))
        return "\n".join(lines)

    def splice(self, text: str, name: str, block: str) -> str:
        """Put a generated block between its markers.

        Args:
            text (str): The guide.
            name (str): The block name.
            block (str): The block.

        Returns:
            str: The guide with the block replaced, unchanged when the markers are missing.
        """
        start, end = self.START.format(name=name), self.END.format(name=name)
        if start not in text or end not in text:
            self.logger.warning("The markers of the %s block are missing: the guide is left as is.", name)
            return text
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        return f"{head}{start}\n{block}\n{end}{tail}"
