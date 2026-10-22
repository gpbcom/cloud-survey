from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Pattern

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.metrics.base import BaseMetricsCrawler, MetricFact
from crawler.metrics.wikidata.enums import WikidataField, WikidataProperty
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource
from models.drivers.facts.company_fact import CompanyFact


class WikidataCrawler(BaseMetricsCrawler):
    """Crawl the company facts of the providers at Wikidata: their founding date and their employees.

    Attributes:
        URL (ClassVar[str]): The entity document, formatted with the item.
        PAGE (ClassVar[str]): The page of an item, formatted with the item.
        UNKNOWN_PART (ClassVar[Pattern[str]]): The month or day `00` of a date known to the year or the month only.
        name (str): The crawler name.
        source (ClassVar[MetricSource]): Wikidata.
        catalogue_url (ClassVar[str]): The Wikidata host.

    Notes:
        - The entity documents (`Special:EntityData/<item>.json`) are the machine-readable form of the items, open
          to crawlers: the SPARQL endpoint is closed to them by its `robots.txt`.
        - A fact is streamed per founding date (P571) and per employee count (P1128, with its date P585 when
          stated). A date known to the year only (`+1999-00-00`) is read as its first day.
    """

    URL: ClassVar[str] = "https://www.wikidata.org/wiki/Special:EntityData/{item}.json"
    PAGE: ClassVar[str] = "https://www.wikidata.org/wiki/{item}"
    UNKNOWN_PART: ClassVar[Pattern[str]] = re.compile(r"-00(?=[-T])")
    name = "wikidata"
    source: ClassVar[MetricSource] = MetricSource.WIKIDATA
    catalogue_url: ClassVar[str] = "https://www.wikidata.org/"

    ############################
    # Internal Helpers Methods #
    ############################

    def _content(self, snak: JsonValue, field: WikidataField) -> Optional[str]:
        """Read a field of the value of a snak.

        Args:
            snak (JsonValue): The snak (a main value or a qualifier).
            field (WikidataField): The field, the time or the amount.

        Returns:
            Optional[str]: The field, `None` when the snak has no such value (an unknown value, another type).
        """
        value = self._as_object(
            self._as_object(self._as_object(snak).get(WikidataField.DATA_VALUE)).get(WikidataField.VALUE)
        )
        found = value.get(field)
        return found if isinstance(found, str) else None

    def _time(self, snak: JsonValue) -> Optional[str]:
        """Read a time value as an ISO date.

        Args:
            snak (JsonValue): The snak.

        Returns:
            Optional[str]: The date, e.g. `2006-03-01T00:00:00Z`, `None` without a time.
        """
        time = self._content(snak, WikidataField.TIME)
        return self.UNKNOWN_PART.sub("-01", time.lstrip("+")) if time else None

    def _statements(self, entity: Dict[str, JsonValue], prop: WikidataProperty) -> List[Dict[str, JsonValue]]:
        """Get the statements of a property.

        Args:
            entity (Dict[str, JsonValue]): The entity.
            prop (WikidataProperty): The property.

        Returns:
            List[Dict[str, JsonValue]]: Its statements, none when the item states nothing.
        """
        found = self._as_object(entity.get(WikidataField.CLAIMS)).get(prop)
        return [self._as_object(statement) for statement in found] if isinstance(found, list) else []

    def _raw_facts(
        self, provider: CloudProvider, item: str, entity: Dict[str, JsonValue]
    ) -> List[Dict[str, JsonValue]]:
        """Get the raw facts of an entity: one per founding date, one per employee count.

        Args:
            provider (CloudProvider): The provider of the item.
            item (str): The item.
            entity (Dict[str, JsonValue]): The entity.

        Returns:
            List[Dict[str, JsonValue]]: The fields of each fact.
        """
        page = self.PAGE.format(item=item)
        raw: List[Dict[str, JsonValue]] = [
            {"provider": provider.value, "item": item, "inception": time, "source_url": page}
            for statement in self._statements(entity, WikidataProperty.INCEPTION)
            if (time := self._time(statement.get(WikidataField.MAIN_SNAK))) is not None
        ]
        for statement in self._statements(entity, WikidataProperty.EMPLOYEES):
            amount = self._content(statement.get(WikidataField.MAIN_SNAK), WikidataField.AMOUNT)
            if amount is None:
                continue
            dates = self._as_object(statement.get(WikidataField.QUALIFIERS)).get(WikidataProperty.POINT_IN_TIME)
            counted = self._time(dates[0]) if isinstance(dates, list) and dates else None
            raw.append(
                {
                    "provider": provider.value,
                    "item": item,
                    "employees": amount.lstrip("+"),
                    "employees_at": counted,
                    "source_url": page,
                }
            )
        return raw

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the entity document of every item of the catalogue.

        Yields:
            Request: A request per item.
        """
        headers = self._headers("application/json")
        for entry in self.catalog.entries:
            if entry.wikidata:
                self.logger.debug("Requesting the Wikidata item %s of %s.", entry.wikidata, entry.provider)
                yield self._metric_request(self.URL.format(item=entry.wikidata), headers, entry.provider)

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        """Extract the company facts of an entity document.

        Args:
            response (Response): The entity document.

        Returns:
            Iterator[MetricFact]: Its founding dates and employee counts.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        provider = self._provider(response)
        if provider is None:
            return
        entities = self._as_object(self._as_object(self._json_body(response)).get(WikidataField.ENTITIES))
        for item, entity in entities.items():
            for raw in self._raw_facts(provider, item, self._as_object(entity)):
                try:
                    yield CompanyFact.model_validate(raw)
                except ValidationError as e:
                    self.logger.warning("Invalid Wikidata statement of %s: %s", item, e.errors()[0]["msg"])
