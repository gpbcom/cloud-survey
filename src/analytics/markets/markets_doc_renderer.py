from __future__ import annotations

# Standard Library Imports.
from collections import Counter
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.markets.correlation.coverage_checker import CoverageChecker
from models.history.chronology import Chronology
from models.markets.enums import AreaKind, Granularity, ShareSource
from models.markets.markets_catalog import MarketsCatalog
from models.markets.series.coverage_entry import CoverageEntry


class MarketsDocRenderer:
    """Print the generated parts of the markets guide: the catalogue, and the coverage of the stored series.

    Attributes:
        START (ClassVar[str]): The opening marker of a generated block, formatted with its name.
        END (ClassVar[str]): The closing marker of a generated block, formatted with its name.
        CATALOGUE (ClassVar[str]): The name of the block printing `conf/history/markets.yaml`.
        COVERAGE (ClassVar[str]): The name of the block printing the stored series.
        checker (CoverageChecker): The correlation thresholds.
        logger (Logger): The renderer logger.

    Notes:
        The guide is hand-written around two generated blocks: the catalogue block follows the YAML (`uv run
        render-markets-doc`, checked by a test), the coverage block follows the stored crawls (`--coverage`, run
        after a markets crawl, since it reads the database).
    """

    START: ClassVar[str] = "<!-- markets:{name}:start -->"
    END: ClassVar[str] = "<!-- markets:{name}:end -->"
    CATALOGUE: ClassVar[str] = "catalogue"
    COVERAGE: ClassVar[str] = "coverage"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            logger (Optional[Logger]): The renderer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.checker = CoverageChecker(self.logger)

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

    def _month(self, day: Optional[date]) -> str:
        """Print a month.

        Args:
            day (Optional[date]): A day of the month.

        Returns:
            str: `YYYY-MM`, or `-`.
        """
        return day.isoformat()[:7] if day else "-"

    def _quarter(self, day: Optional[date]) -> str:
        """Print a quarter.

        Args:
            day (Optional[date]): The first day of the quarter.

        Returns:
            str: `YYYYQn`, or `-`.
        """
        return f"{day.year}Q{(day.month - 1) // 3 + 1}" if day else "-"

    def _coverage_row(self, entry: CoverageEntry) -> List[str]:
        """Print the coverage of a series.

        Args:
            entry (CoverageEntry): The coverage.

        Returns:
            List[str]: The first and last periods, the points, the longest gap and whether it can be correlated.
        """
        printed = self._quarter if entry.granularity is Granularity.QUARTER else self._month
        return [
            printed(entry.first),
            printed(entry.last),
            str(entry.points),
            str(entry.longest_gap),
            "yes" if entry.enough else "no",
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def catalogue(self, catalog: MarketsCatalog, chronology: Chronology) -> str:
        """Print what the markets crawl reads.

        Args:
            catalog (MarketsCatalog): The markets catalogue.
            chronology (Chronology): Names the companies.

        Returns:
            str: The Markdown block (without its markers).
        """
        names = {company.key: company.label for company in chronology.companies}
        lines = ["### Segments", ""]
        lines += self._table(
            ["Segment", "Source", "Statistic", "Devices (default first)", "From", "Definition"],
            [
                [
                    segment.label,
                    segment.source.value,
                    segment.stat.value if segment.stat else "-",
                    ", ".join(device.value for device in segment.devices),
                    segment.first_month
                    or (catalog.statcounter_from if segment.source is ShareSource.STATCOUNTER else "-"),
                    segment.description,
                ]
                for segment in catalog.segments
            ],
        )
        kinds = Counter(area.kind for area in catalog.areas)
        countries = ", ".join(f"{area.label} ({area.key})" for area in catalog.areas if area.kind is AreaKind.COUNTRY)
        unions = "; ".join(
            f"{area.label}: {', '.join(area.members)}" for area in catalog.areas if area.kind is AreaKind.UNION
        )
        lines += [
            "",
            "### Areas",
            "",
            f"{kinds[AreaKind.WORLD]} world, {kinds[AreaKind.CONTINENT]} continents, {kinds[AreaKind.UNION]} union "
            f"and {kinds[AreaKind.COUNTRY]} countries.",
            "",
            f"- **Countries:** {countries}.",
            f"- **Unions (estimated from their members):** {unions}.",
            "",
            "### Listings",
            "",
        ]
        lines += self._table(
            ["Company", "Listing", "Currency", "Primary", "Note"],
            [
                [
                    names.get(listing.company, listing.company),
                    listing.symbol,
                    listing.currency,
                    "yes" if listing.primary else "no",
                    listing.note or "",
                ]
                for listing in catalog.listings
            ],
        )
        lines += ["", "### Valuation points", ""]
        lines += self._table(
            ["Company", "Date", "Kind", "USD bn", "What", "Source", "Tag"],
            [
                [
                    names.get(point.company, point.company),
                    point.date,
                    point.kind.value,
                    f"{point.value_bn:g}" + (f" to {point.high_bn:g}" if point.high_bn else ""),
                    point.label,
                    point.source,
                    point.tag,
                ]
                for point in sorted(catalog.valuations, key=lambda point: point.date)
            ],
        )
        lines += ["", "### Press release families (phase 2)", ""]
        lines += self._table(
            ["Firm", "Segment", "Area", "Search", "Matches (title | caption)", "Excludes"],
            [
                [
                    family.source.value,
                    family.segment,
                    family.area,
                    family.search or "-",
                    f"`{family.pattern}`",
                    f"`{family.exclude}`" if family.exclude else "-",
                ]
                for family in catalog.press
            ],
        )
        lines += ["", "### Manual share points of the dossier (phase 3)", ""]
        lines += self._table(
            ["Segment", "Area", "Period", "Company", "Share %", "Source", "Tag"],
            [
                [share.segment, share.area, share.period, share.label, f"{share.value:g}", share.source, share.tag]
                for share in catalog.manual_shares
            ],
        )
        lines += ["", "### Currencies (FRED, against the US dollar)", ""]
        lines += self._table(
            ["Currency", "Series", "Quoted"],
            [[entry.currency, entry.series, entry.quote.value] for entry in catalog.currencies],
        )
        self.logger.debug("Markets catalogue printed: %d lines.", len(lines))
        return "\n".join(lines)

    def coverage(
        self,
        shares: Dict[Tuple[str, str, str], List[date]],
        listings: Dict[str, List[date]],
        as_of: date,
        quarters: Optional[Dict[Tuple[str, str, str], List[date]]] = None,
    ) -> str:
        """Print the coverage of the stored series, against the correlation thresholds.

        Args:
            shares (Dict[Tuple[str, str, str], List[date]]): The months with shares, by segment, area and device.
            listings (Dict[str, List[date]]): The months with a close, by listing.
            as_of (date): When the coverage was measured.
            quarters (Optional[Dict[Tuple[str, str, str], List[date]]]): The quarters with shares, by segment, area
                and source (the press releases, Synergy, the dossier).

        Returns:
            str: The Markdown block (without its markers).
        """
        share_entries = {key: self.checker.entry(" / ".join(key), months) for key, months in sorted(shares.items())}
        listing_entries = {key: self.checker.entry(key, months) for key, months in sorted(listings.items())}
        quarter_entries = {
            key: self.checker.entry(" / ".join(key), periods, Granularity.QUARTER)
            for key, periods in sorted((quarters or {}).items())
        }
        enough = sum(entry.enough for entry in share_entries.values())
        enough_quarters = sum(entry.enough for entry in quarter_entries.values())
        lines = [
            f"Measured on {as_of.isoformat()}: {len(share_entries)} monthly share series ({enough} long enough to "
            f"correlate), {len(quarter_entries)} quarterly share series ({enough_quarters} long enough) and "
            f"{len(listing_entries)} listings. A series can be correlated with at least "
            f"{CoverageChecker.MIN_POINTS[Granularity.MONTH]} months or "
            f"{CoverageChecker.MIN_POINTS[Granularity.QUARTER]} quarters and no gap over {CoverageChecker.MAX_GAP}.",
            "",
            "### Market shares (months with figures)",
            "",
        ]
        lines += self._table(
            ["Segment", "Area", "Devices", "First", "Last", "Months", "Longest gap", "Correlatable"],
            [[*key, *self._coverage_row(entry)] for key, entry in share_entries.items()],
        )
        lines += ["", "### Market shares (quarters with figures)", ""]
        lines += self._table(
            ["Segment", "Area", "Source", "First", "Last", "Quarters", "Longest gap", "Correlatable"],
            [[*key, *self._coverage_row(entry)] for key, entry in quarter_entries.items()],
        )
        lines += ["", "### Stock values (months with a close)", ""]
        lines += self._table(
            ["Listing", "First", "Last", "Months", "Longest gap", "Correlatable"],
            [[key, *self._coverage_row(entry)] for key, entry in listing_entries.items()],
        )
        self.logger.debug(
            "Markets coverage printed: %d monthly and %d quarterly share series, %d listings.",
            len(share_entries),
            len(quarter_entries),
            len(listing_entries),
        )
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
