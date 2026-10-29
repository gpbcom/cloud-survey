from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Mapping, Optional, Tuple

# Third Party Imports.
from pydantic import JsonValue, ValidationError

# First Party Imports.
from curated.assembly.catalog_splitter import CatalogSplitter
from curated.exception import CuratedCatalogError
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.figures.reported_figures import ReportedFigures
from models.curated.enums import CuratedDataset, IdentifierKind, IdentifierStatus
from models.curated.records.curated_bundle import CuratedBundle
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class CatalogAssembler:
    """Assemble the curated catalogues from their rows: the inverse of `CatalogSplitter`.

    Attributes:
        logger (Logger): The assembler logger.

    Notes:
        - The entries are put back in their rank, the identifier lists filled with the confirmed identifiers of each
          company (the candidates of a resolver and the rejected ones are left out), and the result is validated by
          the catalogue model: the same catalogues as the YAML files gave.
        - The settings (crawler settings of the companies and markets catalogues) are not curated data: they are
          given, from `conf/settings.yaml`.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the assembler.

        Args:
            logger (Optional[Logger]): The assembler logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _bodies(self, bundle: CuratedBundle, dataset: CuratedDataset) -> List[JsonValue]:
        """Get the entries of a section, in their rank.

        Args:
            bundle (CuratedBundle): The rows.
            dataset (CuratedDataset): The section.

        Returns:
            List[JsonValue]: Its entries.
        """
        records = sorted((record for record in bundle.records if record.dataset is dataset), key=lambda r: r.position)
        return [record.body for record in records]

    def _keyed(self, bundle: CuratedBundle, dataset: CuratedDataset) -> Dict[str, JsonValue]:
        """Get the entries of a keyed section (a mapping), in their rank.

        Args:
            bundle (CuratedBundle): The rows.
            dataset (CuratedDataset): The section.

        Returns:
            Dict[str, JsonValue]: Its entries, by key.
        """
        records = sorted((record for record in bundle.records if record.dataset is dataset), key=lambda r: r.position)
        return {record.key: record.body for record in records}

    def _validate[Model: (Chronology, MarketsCatalog, CompaniesCatalog, ReportedFigures, LaunchCatalog)](
        self, catalog: str, model: type[Model], content: Dict[str, JsonValue]
    ) -> Model:
        """Validate an assembled catalogue.

        Args:
            catalog (str): The catalogue, named in the errors.
            model (type[Model]): Its model.
            content (Dict[str, JsonValue]): Its content.

        Returns:
            Model: The catalogue.

        Raises:
            CuratedCatalogError: If the content is invalid.
        """
        try:
            return model.model_validate(content)
        except ValidationError as e:
            self.logger.error("The curated %s catalogue is invalid (%d errors).", catalog, e.error_count())
            raise CuratedCatalogError(catalog, f"the rows are invalid.\n{e}") from e

    def _identifiers(self, bundle: CuratedBundle) -> Dict[Tuple[str, IdentifierKind], List[str]]:
        """Get the confirmed identifiers of each company and kind, in their rank.

        Args:
            bundle (CuratedBundle): The rows.

        Returns:
            Dict[Tuple[str, IdentifierKind], List[str]]: The values, by company and kind.
        """
        confirmed = sorted(
            (item for item in bundle.identifiers if item.status is IdentifierStatus.CONFIRMED),
            key=lambda item: (item.company, item.kind.value, item.position),
        )
        grouped: Dict[Tuple[str, IdentifierKind], List[str]] = {}
        for item in confirmed:
            grouped.setdefault((item.company, item.kind), []).append(item.value)
        return grouped

    ############################
    # Publicly Exposed Methods #
    ############################

    def chronology(self, bundle: CuratedBundle) -> Chronology:
        """Assemble the chronology.

        Args:
            bundle (CuratedBundle): The rows.

        Returns:
            Chronology: The chronology.

        Raises:
            CuratedCatalogError: If the rows do not make a valid chronology.
        """
        as_of = self._bodies(bundle, CuratedDataset.CHRONOLOGY_AS_OF)
        content: Dict[str, JsonValue] = {"as_of": as_of[0] if as_of else None}
        for dataset, field in CatalogSplitter.CHRONOLOGY_LISTS.items():
            content[field] = self._bodies(bundle, dataset)
        chronology = self._validate("chronology", Chronology, content)
        self.logger.debug("Chronology assembled: %d companies.", len(chronology.companies))
        return chronology

    def markets(self, bundle: CuratedBundle, settings: Mapping[str, JsonValue]) -> MarketsCatalog:
        """Assemble the markets catalogue.

        Args:
            bundle (CuratedBundle): The rows.
            settings (Mapping[str, JsonValue]): Its crawler settings (the `markets` block of `conf/settings.yaml`).

        Returns:
            MarketsCatalog: The markets catalogue.

        Raises:
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        content: Dict[str, JsonValue] = dict(settings)
        for dataset, field in CatalogSplitter.MARKETS_LISTS.items():
            content[field] = self._bodies(bundle, dataset)
        content["press_names"] = self._bodies(bundle, CuratedDataset.MARKETS_PRESS_NAMES)
        content["country_currencies"] = self._keyed(bundle, CuratedDataset.MARKETS_COUNTRY_CURRENCIES)
        catalog = self._validate("markets", MarketsCatalog, content)
        self.logger.debug("Markets catalogue assembled: %d segments.", len(catalog.segments))
        return catalog

    def companies(self, bundle: CuratedBundle, settings: Mapping[str, JsonValue]) -> CompaniesCatalog:
        """Assemble the companies catalogue, each company with its confirmed identifiers.

        Args:
            bundle (CuratedBundle): The rows.
            settings (Mapping[str, JsonValue]): Its crawler settings (the `companies` block of `conf/settings.yaml`).

        Returns:
            CompaniesCatalog: The companies catalogue.

        Raises:
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        identifiers = self._identifiers(bundle)
        entries: List[JsonValue] = []
        for profile in sorted(bundle.profiles, key=lambda item: item.position):
            entry: Dict[str, JsonValue] = dict(profile.body)
            for kind, block, field in CatalogSplitter.IDENTIFIERS:
                values: List[JsonValue] = [*identifiers.get((profile.company, kind), [])]
                if not block:
                    entry[field] = values
                    continue
                holder = entry.get(block)
                if isinstance(holder, dict):
                    entry[block] = {**holder, field: values}
            patents = entry.get("patents")
            if isinstance(patents, dict) and not patents.get("assignees"):
                self.logger.warning(
                    "%s has no confirmed patent assignee: its patents are not searched.", profile.company
                )
                entry["patents"] = None
            entries.append(entry)
        catalog = self._validate("companies", CompaniesCatalog, {**settings, "companies": entries})
        self.logger.debug("Companies catalogue assembled: %d companies.", len(catalog.companies))
        return catalog

    def figures(self, bundle: CuratedBundle) -> ReportedFigures:
        """Assemble the researched figures.

        Args:
            bundle (CuratedBundle): The rows.

        Returns:
            ReportedFigures: The researched figures.

        Raises:
            CuratedCatalogError: If the rows do not make valid figures.
        """
        years: Dict[str, List[JsonValue]] = {}
        for year in sorted(bundle.figure_years, key=lambda item: (item.company, item.position)):
            years.setdefault(year.company, []).append(year.body)
        events: Dict[str, List[JsonValue]] = {}
        for event in sorted(bundle.figure_events, key=lambda item: (item.company, item.position)):
            events.setdefault(event.company, []).append(event.body)
        companies: List[JsonValue] = [
            {**company.body, "years": years.get(company.company, []), "events": events.get(company.company, [])}
            for company in sorted(bundle.figure_companies, key=lambda item: item.position)
        ]
        figures = self._validate("figures", ReportedFigures, {"companies": companies})
        self.logger.debug("Researched figures assembled: %d companies.", len(figures.companies))
        return figures

    def launches(self, bundle: CuratedBundle) -> LaunchCatalog:
        """Assemble the launch dates catalogue.

        Args:
            bundle (CuratedBundle): The rows.

        Returns:
            LaunchCatalog: The launch dates catalogue.

        Raises:
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        launches: List[JsonValue] = [launch.body for launch in sorted(bundle.launches, key=lambda item: item.position)]
        content: Dict[str, JsonValue] = {
            "aliases": self._bodies(bundle, CuratedDataset.LAUNCH_ALIASES),
            "launches": launches,
        }
        catalog = self._validate("launches", LaunchCatalog, content)
        self.logger.debug("Launch dates catalogue assembled: %d launches.", len(catalog.launches))
        return catalog
