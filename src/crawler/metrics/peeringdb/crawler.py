from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.metrics.base import BaseMetricsCrawler, MetricFact
from crawler.metrics.peeringdb.enums import PeeringdbField
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource
from models.drivers.facts.network_fact import NetworkFact


class PeeringdbCrawler(BaseMetricsCrawler):
    """Crawl the networks of the providers at PeeringDB: the internet exchanges and facilities they are linked to.

    Attributes:
        URL (ClassVar[str]): The networks document, formatted with the comma-separated autonomous systems.
        name (str): The crawler name.
        source (ClassVar[MetricSource]): PeeringDB.
        catalogue_url (ClassVar[str]): The PeeringDB host.

    Notes:
        - One request reads every network of the catalogue with its links (`depth=2`). A fact is streamed per
          network: `analytics.metrics` counts the exchanges and facilities of each provider.
        - PeeringDB throttles the anonymous queries (HTTP 429). An API key, read from the environment variable named
          by the catalogue, lifts the limit.
    """

    URL: ClassVar[str] = "https://www.peeringdb.com/api/net?asn__in={asns}&depth=2"
    name = "peeringdb"
    source: ClassVar[MetricSource] = MetricSource.PEERINGDB
    catalogue_url: ClassVar[str] = "https://www.peeringdb.com/"

    ############################
    # Internal Helpers Methods #
    ############################

    def _linked(self, network: Dict[str, JsonValue], links: str, key: str) -> List[int]:
        """Get what a network is linked to.

        Args:
            network (Dict[str, JsonValue]): The network.
            links (str): The links, to the exchanges or to the facilities.
            key (str): The linked object of a link.

        Returns:
            List[int]: The PeeringDB identifiers linked.
        """
        found = network.get(links)
        identifiers = [self._as_object(link).get(key) for link in found] if isinstance(found, list) else []
        return [identifier for identifier in identifiers if isinstance(identifier, int)]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request every network of the catalogue at once.

        Yields:
            Request: The networks request, if the catalogue holds autonomous systems.
        """
        asns = sorted({asn for entry in self.catalog.entries for asn in entry.asns})
        headers = self._headers("application/json")
        key = self._secret(self.catalog.peeringdb_key_env)
        if key:
            headers["Authorization"] = f"Api-Key {key}"
        if asns:
            self.logger.debug("Requesting %d PeeringDB networks.", len(asns))
            yield self._metric_request(self.URL.format(asns=",".join(map(str, asns))), headers)

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        """Extract the networks of the providers.

        Args:
            response (Response): The networks document.

        Returns:
            Iterator[MetricFact]: A fact per network of a provider of the catalogue.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        owners: Dict[int, CloudProvider] = {asn: entry.provider for entry in self.catalog.entries for asn in entry.asns}
        networks = self._as_object(self._json_body(response)).get(PeeringdbField.DATA)
        for network in [self._as_object(item) for item in networks] if isinstance(networks, list) else []:
            asn = network.get(PeeringdbField.ASN)
            provider = owners.get(asn) if isinstance(asn, int) else None
            if provider is None:
                continue
            try:
                yield NetworkFact(
                    provider=provider,
                    asn=asn,
                    exchanges=self._linked(network, PeeringdbField.EXCHANGE_LINKS, PeeringdbField.EXCHANGE),
                    facilities=self._linked(network, PeeringdbField.FACILITY_LINKS, PeeringdbField.FACILITY),
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid PeeringDB network %s: %s", asn, e.errors()[0]["msg"])
