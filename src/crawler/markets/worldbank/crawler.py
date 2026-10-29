from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Iterator, List, Optional, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.markets.base import BaseMarketsCrawler, MarketFact
from crawler.markets.worldbank.enums import WorldBankField
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import AreaKind, MarketFeed, WeightIndicator
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog


class WorldBankCrawler(BaseMarketsCrawler):
    """Crawl the World Bank internet users and population of the union members and of the catalogue's countries.

    Attributes:
        URL (ClassVar[str]): The indicator document of a list of countries, formatted with them and the indicator.
        FIRST_YEAR (ClassVar[int]): The first year read (one before StatCounter's first).
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): The World Bank.
        catalogue_url (ClassVar[str]): The World Bank API host.

    Notes:
        - Two documents per union: the share of the population using the internet (`IT.NET.USER.ZS`) and the
          population (`SP.POP.TOTL`) of each member, per year. Their product is the member's internet users, its
          weight in the union estimate (`analytics.markets`).
        - The countries of the catalogue are read too: the home internet users of the providers' companies are a
          criterion of the Rise drivers. The World Bank has no Taiwan.
        - The latest years are often missing (`null`): they are left out, the estimate carries the last known
          year forward.
        - The World Bank data are open (CC BY 4.0) and the API host has no `robots.txt`.
    """

    URL: ClassVar[str] = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
    FIRST_YEAR: ClassVar[int] = 2008
    name = "worldbank"
    feed: ClassVar[MarketFeed] = MarketFeed.WORLD_BANK
    catalogue_url: ClassVar[str] = "https://api.worldbank.org/"

    def __init__(
        self,
        catalog: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            catalog (Optional[MarketsCatalog]): What is read, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(catalog=catalog, scope=scope, crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _countries(self) -> List[str]:
        """Get the member countries of every union, then the other countries of the catalogue.

        Returns:
            List[str]: The countries, each once.
        """
        members = [member for area in self.catalog.areas if area.kind is AreaKind.UNION for member in area.members]
        countries = [area.key for area in self.catalog.areas if area.kind is AreaKind.COUNTRY]
        return [*dict.fromkeys(members + countries)]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request both indicators for the union members and the countries of the catalogue.

        Yields:
            Request: A request per indicator.
        """
        members = self._countries()
        if not members:
            self.logger.warning("The markets catalogue has no country: no World Bank weight to read.")
            return
        query = urlencode({"format": "json", "date": f"{self.FIRST_YEAR}:{datetime.now(UTC).year}", "per_page": 5000})
        headers = self._headers("application/json")
        for indicator in WeightIndicator:
            url = self.URL.format(countries=";".join(members), indicator=indicator.value)
            self.logger.debug("Requesting %s for %d countries.", indicator.value, len(members))
            yield self._market_request(f"{url}?{query}", headers, **{WorldBankField.INDICATOR: indicator.value})

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the yearly values of an indicator document.

        Args:
            response (Response): The document: `[paging, [observation, …]]`.

        Returns:
            Iterator[MarketFact]: A value per country and year, the missing ones left out.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        document = self._json_body(response)
        rows = document[1] if isinstance(document, list) and len(document) > 1 else None
        if not isinstance(rows, list):
            self.logger.warning("The World Bank document %s holds no observation.", response.url)
            return
        indicator = response.meta.get(WorldBankField.INDICATOR)
        for row in rows:
            entry = self._as_object(row)
            value = entry.get(WorldBankField.VALUE)
            if value is None:
                continue
            try:
                yield WeightObservation(
                    indicator=indicator,
                    country=self._as_object(entry.get(WorldBankField.COUNTRY)).get(WorldBankField.ID),
                    year=entry.get(WorldBankField.DATE),
                    value=value,
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid %s value in %s: %s", indicator, response.url, e.errors()[0]["msg"])
