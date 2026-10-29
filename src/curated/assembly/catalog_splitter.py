from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple

# Third Party Imports.
from pydantic import BaseModel, JsonValue

# First Party Imports.
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.figures.reported_figures import ReportedFigures
from models.curated.companies.company_identifier import CompanyIdentifier
from models.curated.companies.company_profile import CompanyProfile
from models.curated.enums import CuratedDataset, IdentifierKind
from models.curated.figures.reported_company_record import ReportedCompanyRecord
from models.curated.figures.reported_event_record import ReportedEventRecord
from models.curated.figures.reported_year_record import ReportedYearRecord
from models.curated.launches.product_launch import ProductLaunch
from models.curated.records.curated_bundle import CuratedBundle
from models.curated.records.curated_record import CuratedRecord
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class CatalogSplitter:
    """Split the curated catalogues into the rows they are stored as: a record, a profile, an identifier per entry.

    Attributes:
        CHRONOLOGY_LISTS (ClassVar[Dict[CuratedDataset, str]]): The list field of the chronology of each section.
        MARKETS_LISTS (ClassVar[Dict[CuratedDataset, str]]): The list field of the markets catalogue of each section.
        KEYS (ClassVar[Dict[CuratedDataset, Tuple[str, ...]]]): The fields making the natural key of an entry.
        IDENTIFIERS (ClassVar[List[Tuple[IdentifierKind, str, str]]]): Where each kind of identifier is in a company
            entry: the block (empty for the entry itself) and the list field.
        logger (Logger): The splitter logger.

    Notes:
        - Every row keeps its entry as the catalogue model writes it (`model_dump(mode="json")`) and its rank, so
          that `CatalogAssembler` gives back the same catalogues.
        - The notes (what the research wrote beside an entry) are given by key: `<dataset>|<key>` for a record,
          `company|<company>`, `identifier|<company>|<kind>|<value>`, `figures|<company>`,
          `figure-year|<company>|<fiscal year>`, `figure-event|<company>|<rank>`, `launch|<crawler>|<name>`.
    """

    CHRONOLOGY_LISTS: ClassVar[Dict[CuratedDataset, str]] = {
        CuratedDataset.CHRONOLOGY_SEGMENTS: "segments",
        CuratedDataset.CHRONOLOGY_COMPANIES: "companies",
        CuratedDataset.CHRONOLOGY_REIGNS: "reigns",
        CuratedDataset.CHRONOLOGY_EVENTS: "events",
    }
    MARKETS_LISTS: ClassVar[Dict[CuratedDataset, str]] = {
        CuratedDataset.MARKETS_SEGMENTS: "segments",
        CuratedDataset.MARKETS_AREAS: "areas",
        CuratedDataset.MARKETS_LABELS: "labels",
        CuratedDataset.MARKETS_CURRENCIES: "currencies",
        CuratedDataset.MARKETS_REGIONS: "regions",
        CuratedDataset.MARKETS_LISTINGS: "listings",
        CuratedDataset.MARKETS_VALUATIONS: "valuations",
        CuratedDataset.MARKETS_PRESS: "press",
        CuratedDataset.MARKETS_MANUAL_SHARES: "manual_shares",
    }
    KEYS: ClassVar[Dict[CuratedDataset, Tuple[str, ...]]] = {
        CuratedDataset.CHRONOLOGY_SEGMENTS: ("key",),
        CuratedDataset.CHRONOLOGY_COMPANIES: ("key",),
        CuratedDataset.CHRONOLOGY_REIGNS: ("segment", "company", "start"),
        CuratedDataset.CHRONOLOGY_EVENTS: ("key",),
        CuratedDataset.MARKETS_SEGMENTS: ("key",),
        CuratedDataset.MARKETS_AREAS: ("key",),
        CuratedDataset.MARKETS_LABELS: ("source", "label"),
        CuratedDataset.MARKETS_CURRENCIES: ("currency",),
        CuratedDataset.MARKETS_REGIONS: ("key",),
        CuratedDataset.MARKETS_LISTINGS: ("company", "symbol"),
        CuratedDataset.MARKETS_VALUATIONS: ("company", "date", "kind"),
        CuratedDataset.MARKETS_PRESS: ("source", "segment", "area"),
        CuratedDataset.MARKETS_MANUAL_SHARES: ("segment", "area", "period", "label", "company"),
        CuratedDataset.LAUNCH_ALIASES: ("crawler", "name"),
    }
    IDENTIFIERS: ClassVar[List[Tuple[IdentifierKind, str, str]]] = [
        (IdentifierKind.SEC_CIK, "", "sec_ciks"),
        (IdentifierKind.PATENT_ASSIGNEE, "patents", "assignees"),
        (IdentifierKind.PATENT_EXCLUDE, "patents", "exclude"),
        (IdentifierKind.OPENALEX_INSTITUTION, "openalex", "institutions"),
        (IdentifierKind.OPENALEX_INCLUDE, "openalex", "include_affiliations"),
        (IdentifierKind.OPENALEX_EXCLUDE, "openalex", "exclude_affiliations"),
    ]

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the splitter.

        Args:
            logger (Optional[Logger]): The splitter logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _key(self, dataset: CuratedDataset, body: JsonValue) -> str:
        """Write the natural key of an entry.

        Args:
            dataset (CuratedDataset): Its section.
            body (JsonValue): The entry.

        Returns:
            str: The values of its key fields, joined by `|`.
        """
        fields = body if isinstance(body, dict) else {}
        return "|".join("" if fields.get(name) is None else str(fields.get(name)) for name in self.KEYS[dataset])

    def _records(
        self, model: BaseModel, sections: Dict[CuratedDataset, str], notes: Mapping[str, str]
    ) -> List[CuratedRecord]:
        """Split the list fields of a catalogue into records.

        Args:
            model (BaseModel): The catalogue.
            sections (Dict[CuratedDataset, str]): The list field of each section.
            notes (Mapping[str, str]): The notes, by key.

        Returns:
            List[CuratedRecord]: A record per entry, in the order of the catalogue.
        """
        dumped = model.model_dump(mode="json")
        records: List[CuratedRecord] = []
        for dataset, field in sections.items():
            entries = dumped.get(field)
            for position, body in enumerate(entries if isinstance(entries, list) else []):
                key = self._key(dataset, body)
                records.append(
                    CuratedRecord(
                        dataset=dataset, key=key, position=position, body=body, note=notes.get(f"{dataset}|{key}")
                    )
                )
        return records

    def _identifiers(
        self, company: str, entry: Dict[str, JsonValue], notes: Mapping[str, str]
    ) -> Tuple[Dict[str, JsonValue], List[CompanyIdentifier]]:
        """Take the identifiers out of a company entry.

        Args:
            company (str): The company key.
            entry (Dict[str, JsonValue]): Its entry, as the catalogue writes it.
            notes (Mapping[str, str]): The notes, by key.

        Returns:
            Tuple[Dict[str, JsonValue], List[CompanyIdentifier]]: The entry with its identifier lists emptied, then
                its identifiers, in their order.
        """
        body: Dict[str, JsonValue] = dict(entry)
        identifiers: List[CompanyIdentifier] = []
        for kind, block, field in self.IDENTIFIERS:
            holder = body if not block else body.get(block)
            if not isinstance(holder, dict):
                continue
            if block:
                holder = dict(holder)
                body[block] = holder
            values = holder.get(field)
            for position, value in enumerate(values if isinstance(values, list) else []):
                identifiers.append(
                    CompanyIdentifier(
                        company=company,
                        kind=kind,
                        value=str(value),
                        position=position,
                        note=notes.get(f"identifier|{company}|{kind}|{value}"),
                    )
                )
            holder[field] = []
        return body, identifiers

    ############################
    # Publicly Exposed Methods #
    ############################

    def chronology(self, chronology: Chronology, notes: Optional[Mapping[str, str]] = None) -> List[CuratedRecord]:
        """Split the chronology into records.

        Args:
            chronology (Chronology): The chronology.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            List[CuratedRecord]: Its month, then a record per segment, company, reign and event.
        """
        found = notes or {}
        as_of = CuratedRecord(
            dataset=CuratedDataset.CHRONOLOGY_AS_OF,
            key="as-of",
            position=0,
            body=chronology.as_of,
            note=found.get(f"{CuratedDataset.CHRONOLOGY_AS_OF}|as-of"),
        )
        records = [as_of, *self._records(chronology, self.CHRONOLOGY_LISTS, found)]
        self.logger.debug("Chronology split into %d records.", len(records))
        return records

    def markets(self, catalog: MarketsCatalog, notes: Optional[Mapping[str, str]] = None) -> List[CuratedRecord]:
        """Split the markets catalogue into records (its settings are not curated data: they are left out).

        Args:
            catalog (MarketsCatalog): The markets catalogue.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            List[CuratedRecord]: A record per entry of each list, per press name and per country currency.
        """
        found = notes or {}
        records = self._records(catalog, self.MARKETS_LISTS, found)
        for position, name in enumerate(catalog.press_names):
            dataset = CuratedDataset.MARKETS_PRESS_NAMES
            records.append(
                CuratedRecord(
                    dataset=dataset, key=name, position=position, body=name, note=found.get(f"{dataset}|{name}")
                )
            )
        for position, (country, currency) in enumerate(catalog.country_currencies.items()):
            dataset = CuratedDataset.MARKETS_COUNTRY_CURRENCIES
            records.append(
                CuratedRecord(
                    dataset=dataset,
                    key=country,
                    position=position,
                    body=currency,
                    note=found.get(f"{dataset}|{country}"),
                )
            )
        self.logger.debug("Markets catalogue split into %d records.", len(records))
        return records

    def companies(
        self, catalog: CompaniesCatalog, notes: Optional[Mapping[str, str]] = None
    ) -> Tuple[List[CompanyProfile], List[CompanyIdentifier]]:
        """Split the companies catalogue into profiles and identifiers (its settings are left out).

        Args:
            catalog (CompaniesCatalog): The companies catalogue.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            Tuple[List[CompanyProfile], List[CompanyIdentifier]]: A profile per company, then its identifiers.
        """
        found = notes or {}
        profiles: List[CompanyProfile] = []
        identifiers: List[CompanyIdentifier] = []
        for position, entry in enumerate(catalog.companies):
            body, owned = self._identifiers(entry.key, entry.model_dump(mode="json"), found)
            profiles.append(
                CompanyProfile(company=entry.key, position=position, body=body, note=found.get(f"company|{entry.key}"))
            )
            identifiers.extend(owned)
        self.logger.debug("Companies split into %d profiles, %d identifiers.", len(profiles), len(identifiers))
        return profiles, identifiers

    def figures(
        self, figures: ReportedFigures, notes: Optional[Mapping[str, str]] = None
    ) -> Tuple[List[ReportedCompanyRecord], List[ReportedYearRecord], List[ReportedEventRecord]]:
        """Split the researched figures into companies, years and events.

        Args:
            figures (ReportedFigures): The researched figures.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            Tuple[List[ReportedCompanyRecord], List[ReportedYearRecord], List[ReportedEventRecord]]: The rows.
        """
        found = notes or {}
        companies: List[ReportedCompanyRecord] = []
        years: List[ReportedYearRecord] = []
        events: List[ReportedEventRecord] = []
        for position, entry in enumerate(figures.companies):
            body = entry.model_dump(mode="json")
            year_bodies, event_bodies = body.pop("years"), body.pop("events")
            body.update({"years": [], "events": []})
            companies.append(
                ReportedCompanyRecord(
                    company=entry.company, position=position, body=body, note=found.get(f"figures|{entry.company}")
                )
            )
            for rank, year in enumerate(year_bodies if isinstance(year_bodies, list) else []):
                fiscal_year = year.get("fiscal_year") if isinstance(year, dict) else None
                years.append(
                    ReportedYearRecord(
                        company=entry.company,
                        fiscal_year=fiscal_year if isinstance(fiscal_year, int) else 0,
                        position=rank,
                        body=year if isinstance(year, dict) else {},
                        note=found.get(f"figure-year|{entry.company}|{fiscal_year}"),
                    )
                )
            for rank, event in enumerate(event_bodies if isinstance(event_bodies, list) else []):
                events.append(
                    ReportedEventRecord(
                        company=entry.company,
                        position=rank,
                        body=event if isinstance(event, dict) else {},
                        note=found.get(f"figure-event|{entry.company}|{rank}"),
                    )
                )
        self.logger.debug("Figures split: %d companies, %d years, %d events.", len(companies), len(years), len(events))
        return companies, years, events

    def launches(
        self, catalog: LaunchCatalog, notes: Optional[Mapping[str, str]] = None
    ) -> Tuple[List[ProductLaunch], List[CuratedRecord]]:
        """Split the launch dates catalogue into launches and alias records.

        Args:
            catalog (LaunchCatalog): The launch dates catalogue.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            Tuple[List[ProductLaunch], List[CuratedRecord]]: The launches, then the aliases.
        """
        found = notes or {}
        launches = [
            ProductLaunch(
                crawler=launch.crawler,
                name=launch.name,
                position=position,
                body=launch.model_dump(mode="json"),
                note=found.get(f"launch|{launch.crawler}|{launch.name}"),
            )
            for position, launch in enumerate(catalog.launches)
        ]
        aliases = self._records(catalog, {CuratedDataset.LAUNCH_ALIASES: "aliases"}, found)
        self.logger.debug("Launches split: %d launches, %d aliases.", len(launches), len(aliases))
        return launches, aliases

    def bundle(
        self,
        chronology: Chronology,
        markets: MarketsCatalog,
        companies: CompaniesCatalog,
        figures: ReportedFigures,
        launches: LaunchCatalog,
        notes: Optional[Mapping[str, str]] = None,
    ) -> CuratedBundle:
        """Split every curated catalogue into the bundle of its rows.

        Args:
            chronology (Chronology): The chronology.
            markets (MarketsCatalog): The markets catalogue.
            companies (CompaniesCatalog): The companies catalogue.
            figures (ReportedFigures): The researched figures.
            launches (LaunchCatalog): The launch dates catalogue.
            notes (Optional[Mapping[str, str]]): The notes, by key.

        Returns:
            CuratedBundle: Every row.
        """
        profiles, identifiers = self.companies(companies, notes)
        figure_companies, figure_years, figure_events = self.figures(figures, notes)
        launch_rows, aliases = self.launches(launches, notes)
        records: Sequence[CuratedRecord] = [
            *self.chronology(chronology, notes),
            *self.markets(markets, notes),
            *aliases,
        ]
        bundle = CuratedBundle(
            records=list(records),
            profiles=profiles,
            identifiers=identifiers,
            figure_companies=figure_companies,
            figure_years=figure_years,
            figure_events=figure_events,
            launches=launch_rows,
        )
        self.logger.info("Curated catalogues split: %d records, %d launches.", len(bundle.records), len(launch_rows))
        return bundle
