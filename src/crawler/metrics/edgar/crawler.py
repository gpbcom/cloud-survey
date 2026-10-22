from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Tuple

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.metrics.base import BaseMetricsCrawler, MetricFact
from crawler.metrics.edgar.enums import EdgarField
from models.drivers.enums import MetricSource
from models.drivers.facts.capex_fact import CapexFact


class EdgarCrawler(BaseMetricsCrawler):
    """Crawl the capital expenditure facts of the groups filing at the SEC (EDGAR XBRL `companyfacts`).

    Attributes:
        URL (ClassVar[str]): The `companyfacts` document, formatted with the 10-digit CIK.
        FILINGS (ClassVar[Tuple[str, ...]]): The prefixes of the forms read: the quarterly and annual reports.
        name (str): The crawler name.
        source (ClassVar[MetricSource]): SEC EDGAR.
        catalogue_url (ClassVar[str]): The EDGAR data host.

    Notes:
        - `companyfacts` holds the facts without dimension: the capex is the group's (Amazon, not AWS alone).
        - Every fact of the capex concepts of the catalogue is streamed as filed, the year-to-date ones included:
          `analytics.metrics` derives the quarters.
        - SEC EDGAR asks for a user agent naming a contact, read from the environment variable of the catalogue.
    """

    URL: ClassVar[str] = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    FILINGS: ClassVar[Tuple[str, ...]] = ("10-Q", "10-K")
    name = "edgar"
    source: ClassVar[MetricSource] = MetricSource.EDGAR
    catalogue_url: ClassVar[str] = "https://data.sec.gov/"

    ############################
    # Internal Helpers Methods #
    ############################

    def _concept_facts(self, document: JsonValue, concept: str) -> List[Dict[str, JsonValue]]:
        """Get the dollar facts of a concept.

        Args:
            document (JsonValue): The `companyfacts` document.
            concept (str): The US-GAAP concept.

        Returns:
            List[Dict[str, JsonValue]]: Its facts in dollars, none when the group does not report it.
        """
        facts = self._as_object(self._as_object(document).get(EdgarField.FACTS))
        units = self._as_object(
            self._as_object(self._as_object(facts.get(EdgarField.US_GAAP)).get(concept)).get(EdgarField.UNITS)
        )
        found = units.get(EdgarField.USD)
        return [self._as_object(fact) for fact in found] if isinstance(found, list) else []

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the `companyfacts` document of every group of the catalogue with a CIK.

        Yields:
            Request: A request per filer.
        """
        headers = self._headers("application/json")
        headers["User-Agent"] = self._secret(self.catalog.sec_user_agent_env) or self.catalog.user_agent
        for entry in self.catalog.entries:
            if entry.cik is not None:
                self.logger.debug("Requesting the SEC EDGAR facts of %s (CIK %s).", entry.provider, entry.cik)
                yield self._metric_request(self.URL.format(cik=entry.cik), headers, entry.provider)

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        """Extract the capex facts of a `companyfacts` document.

        Args:
            response (Response): The document.

        Returns:
            Iterator[MetricFact]: The capex facts of the quarterly and annual reports.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        provider = self._provider(response)
        if provider is None:
            return
        document = self._json_body(response)
        found = 0
        for concept in self.catalog.capex_concepts:
            for fact in self._concept_facts(document, concept):
                if not str(fact.get(EdgarField.FORM, "")).startswith(self.FILINGS):
                    continue
                try:
                    yield CapexFact(
                        provider=provider,
                        concept=concept,
                        start=fact.get(EdgarField.START),
                        end=fact.get(EdgarField.END),
                        value=fact.get(EdgarField.VALUE),
                        form=fact.get(EdgarField.FORM),
                        source_url=response.url,
                    )
                    found += 1
                except ValidationError as e:
                    self.logger.warning("Invalid %s fact in %s: %s", concept, response.url, e.errors()[0]["msg"])
        if not found:
            self.logger.warning("No capex fact for %s in %s.", provider, response.url)
