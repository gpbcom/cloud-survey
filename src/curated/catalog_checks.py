from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Set

# First Party Imports.
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.figures.reported_figures import ReportedFigures
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class CatalogChecks:
    """Check the curated catalogues against the chronology, the list of the companies and segments they may name.

    Attributes:
        logger (Logger): The checks logger.

    Notes:
        - The chronology defines every company key: the companies, the markets and the researched figures must only
          name its companies, so that the charts can draw each in its colour.
        - The checks only report: the YAML loaders and the database provider raise their own errors, so that both
          read the same catalogues the same way.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the checks.

        Args:
            logger (Optional[Logger]): The checks logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _keys(self, chronology: Chronology) -> Set[str]:
        """Get the companies of the chronology.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            Set[str]: Their keys.
        """
        return {company.key for company in chronology.companies}

    ############################
    # Publicly Exposed Methods #
    ############################

    def unknown_companies(self, catalog: CompaniesCatalog, chronology: Chronology) -> List[str]:
        """Get the companies of the companies catalogue the chronology does not define.

        Args:
            catalog (CompaniesCatalog): The companies catalogue.
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The unknown companies, sorted.
        """
        unknown = sorted({entry.key for entry in catalog.companies} - self._keys(chronology))
        if unknown:
            self.logger.warning("The companies catalogue names companies outside the chronology: %s", unknown)
        return unknown

    def uncrawled_companies(self, catalog: CompaniesCatalog, chronology: Chronology) -> List[str]:
        """Get the companies of the chronology the companies catalogue leaves out (they are not crawled).

        Args:
            catalog (CompaniesCatalog): The companies catalogue.
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The companies left out, sorted.
        """
        missing = sorted(self._keys(chronology) - {entry.key for entry in catalog.companies})
        self.logger.debug("%d companies of the chronology are not crawled.", len(missing))
        return missing

    def unknown_figure_companies(self, figures: ReportedFigures, chronology: Chronology) -> List[str]:
        """Get the companies of the researched figures the chronology does not define.

        Args:
            figures (ReportedFigures): The researched figures.
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The unknown companies, sorted.
        """
        unknown = sorted({entry.company for entry in figures.companies} - self._keys(chronology))
        if unknown:
            self.logger.warning("The researched figures name companies outside the chronology: %s", unknown)
        return unknown

    def unknown_market_companies(self, catalog: MarketsCatalog, chronology: Chronology) -> List[str]:
        """Get the companies of a label, a listing, a valuation or a manual share the chronology does not define.

        Args:
            catalog (MarketsCatalog): The markets catalogue.
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The unknown companies, sorted.
        """
        named = {entry.company for entry in catalog.labels}
        named |= {listing.company for listing in catalog.listings}
        named |= {point.company for point in catalog.valuations}
        named |= {share.company for share in catalog.manual_shares if share.company}
        unknown = sorted(named - self._keys(chronology))
        if unknown:
            self.logger.warning("The markets catalogue names companies outside the chronology: %s", unknown)
        return unknown

    def unknown_segment_links(self, catalog: MarketsCatalog, chronology: Chronology) -> List[str]:
        """Get the market segments linking a chronology segment the chronology does not define.

        Args:
            catalog (MarketsCatalog): The markets catalogue.
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The market segments with an unknown link, in their order.
        """
        segments = {segment.key for segment in chronology.segments}
        wrong = [
            segment.key for segment in catalog.segments if segment.chronology and segment.chronology not in segments
        ]
        for key in wrong:
            self.logger.warning("The market segment %s links an unknown chronology segment.", key)
        return wrong
