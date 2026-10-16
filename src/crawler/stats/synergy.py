from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.stats.base import BaseStatsCrawler
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport
from models.stats.market_share import MarketShare
from models.stats.provider_mention import ProviderMention


class SynergyResearchCrawler(BaseStatsCrawler):
    """Synergy Research Group cloud market share crawler.

    Attributes:
        QUALIFIER (ClassVar[str]): The wording of an approximate figure, e.g. "around 15%" or "well over $27 billion".
        PERIMETER (ClassVar[str]): The fixed wording of the cloud infrastructure services perimeter.
        NUMBER (ClassVar[str]): A figure, with or without decimals.
        ARTICLES_URL (ClassVar[str]): The press releases page, listing the articles published since 2023.
        CDX_URL (ClassVar[str]): The Wayback Machine CDX query listing every article ever archived, back to 2013.
        FIRST_YEAR (ClassVar[int]): The first year of the reported periods. The older articles measure a narrower
            perimeter (the shares are given on public IaaS and PaaS only).
        SHARE_TOTAL (ClassVar[Tuple[float, float]]): The plausible range of the Amazon, Microsoft and Google shares
            summed, in percent.
        ORDINALS (ClassVar[Dict[str, int]]): The ordinal words of the ranks and of the quarters or half-years.
        KNOWN_PROVIDERS (ClassVar[Tuple[str, ...]]): The provider names reported as mentions when an article names
            them without a market share.
        NAMED_PLAYERS (ClassVar[Dict[str, MarketPlayer]]): The names of the players which may have a market share.
        CLOUD_WORDING (ClassVar[re.Pattern[str]]): The titles (or slug words) of the cloud market articles.
        ARTICLE_PATH (ClassVar[re.Pattern[str]]): The path of an article, giving its slug.
        DATELINE (ClassVar[re.Pattern[str]]): The dateline of a press release, giving its publication date.
        ALT_QUARTER (ClassVar[re.Pattern[str]]): The quarter of a chart image alt text, e.g. `CIS Q226`.
        WORLD_SIZE (ClassVar[re.Pattern[str]]): The worldwide quarterly market size sentence.
        TWELVE_MONTH (ClassVar[re.Pattern[str]]): The trailing twelve-month or full-year revenues.
        GROWTH (ClassVar[re.Pattern[str]]): The year-on-year growth of the market, in its several wordings.
        SHARES (ClassVar[re.Pattern[str]]): The worldwide shares given by position: Amazon, Microsoft and Google, or
            Microsoft and Google only.
        PLAYER_SHARES (ClassVar[Dict[MarketPlayer, re.Pattern[str]]]): The share of a player stated on its own, e.g.
            the Amazon share band "32-34%".
        BIG_THREE (ClassVar[re.Pattern[str]]): The combined worldwide share of Amazon, Microsoft and Google.
        PUBLIC_GROWTH (ClassVar[re.Pattern[str]]): The growth of the public IaaS and PaaS segment.
        PUBLIC_TOP_THREE (ClassVar[re.Pattern[str]]): The combined share of the top three in public IaaS and PaaS.
        METHODOLOGY_BREAK (ClassVar[re.Pattern[str]]): The note of a reclassification, e.g. in the Q3 2024 release.
        EUROPE_WORDING (ClassVar[re.Pattern[str]]): The wording of the European market articles.
        EUROPE_MARKET (ClassVar[re.Pattern[str]]): The European market size of a year or a quarter, in EUR.
        EUROPE_HALF (ClassVar[re.Pattern[str]]): The European market size of a half-year, in EUR.
        EUROPE_TWELVE_MONTH (ClassVar[re.Pattern[str]]): The European revenues of the last four quarters, in EUR.
        EUROPE_BIG_THREE (ClassVar[re.Pattern[str]]): The combined European share of the three global leaders.
        EUROPE_PROVIDERS (ClassVar[re.Pattern[str]]): The combined share of the European providers.
        EUROPE_LEADERS (ClassVar[re.Pattern[str]]): The share of the leading European providers (SAP, Deutsche
            Telekom).
        RANK (ClassVar[re.Pattern[str]]): The rank of a provider, e.g. "fourth-placed Alibaba".
        name (str): The crawler name.
        source (ClassVar[str]): The market research firm.
        catalogue_url (ClassVar[str]): The press releases page.
        complement_urls (ClassVar[Tuple[str, ...]]): The Wayback Machine CDX query, for the older articles.
        download_delay (float): The delay between two requests, in seconds.
        requested_slugs (Set[str]): The slugs of the articles already requested.

    Notes:
        - Synergy publishes its figures in the text of its press releases (`www.srgresearch.com`, plain server-rendered
          HTML, no sitemap and no RSS). The `/articles` page lists the articles since 2023: the links whose title is
          about the cloud market are followed. The older articles are still online but no longer linked: their slugs
          are read from the Wayback Machine CDX API, filtered on the same wording, and the articles are fetched live.
          Each article is requested once.
        - An article is kept when it holds the worldwide cloud infrastructure services sentence (market size, then the
          Amazon, Microsoft and Google shares, the big three combined share and the public IaaS and PaaS figures) or the
          European cloud market wording (market size in EUR, the big three and the European providers shares). The
          quarter is the calendar quarter before the publication date (a February release covers the fourth quarter of
          the previous year), cross-checked with the chart alt text. The providers named without a share are listed as
          mentions, with their rank when given.
    """

    QUALIFIER: ClassVar[str] = (
        r"(?:around|almost|close to|nearly|about|approximately|just under|well under|under|just over|well over|over|~)"
    )
    PERIMETER: ClassVar[str] = (
        r"cloud infrastructure service revenues \(including IaaS, PaaS and hosted private cloud services\)"
    )
    NUMBER: ClassVar[str] = r"\d+(?:\.\d+)?"
    ARTICLES_URL: ClassVar[str] = "https://www.srgresearch.com/articles"
    CDX_URL: ClassVar[str] = (
        "https://web.archive.org/cdx/search/cdx?url=srgresearch.com/articles/&matchType=prefix&fl=original"
        "&collapse=urlkey&filter=statuscode:200&output=json"
    )
    FIRST_YEAR: ClassVar[int] = 2021
    SHARE_TOTAL: ClassVar[Tuple[float, float]] = (55.0, 75.0)
    ORDINALS: ClassVar[Dict[str, int]] = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    KNOWN_PROVIDERS: ClassVar[Tuple[str, ...]] = (
        "Alibaba",
        "Oracle",
        "Salesforce",
        "IBM",
        "Huawei",
        "Tencent",
        "Baidu",
        "China Telecom",
        "China Mobile",
        "China Unicom",
        "Rackspace",
        "Snowflake",
        "MongoDB",
        "VMware",
        "CoreWeave",
        "Nebius",
        "Crusoe",
        "Lambda",
        "OpenAI",
        "Anthropic",
        "Databricks",
        "Nscale",
        "OVHcloud",
        "Orange",
        "Telecom Italia",
        "Deutsche Telekom",
        "SAP",
        "IONOS",
        "Scaleway",
        "Hetzner",
    )
    NAMED_PLAYERS: ClassVar[Dict[str, MarketPlayer]] = {
        "Amazon": MarketPlayer.AMAZON,
        "AWS": MarketPlayer.AMAZON,
        "Microsoft": MarketPlayer.MICROSOFT,
        "Azure": MarketPlayer.MICROSOFT,
        "Google": MarketPlayer.GOOGLE,
        "SAP": MarketPlayer.SAP,
        "Deutsche Telekom": MarketPlayer.DEUTSCHE_TELEKOM,
    }
    CLOUD_WORDING: ClassVar[re.Pattern[str]] = re.compile(
        r"\bcloud (?:market|spending|revenues)\b|\bQ[1-4]\b.*\bcloud\b|\bcloud\b.*\bQ[1-4]\b|\bcloud\b.*\bmarket share"
        r"|\beuropean cloud\b|\b(?:amazon|aws)\b.*\bmicrosoft\b.*\bmarket\b",
        re.IGNORECASE,
    )
    ARTICLE_PATH: ClassVar[re.Pattern[str]] = re.compile(r"/articles/([^/]+)/?")
    DATELINE: ClassVar[re.Pattern[str]] = re.compile(r"RENO, ?NV,? ([A-Z][a-z]+ \d{1,2}, \d{4})")
    ALT_QUARTER: ClassVar[re.Pattern[str]] = re.compile(r"\bQ([1-4])(\d{2})\b", re.IGNORECASE)
    WORLD_SIZE: ClassVar[re.Pattern[str]] = re.compile(
        rf"(?<!European ){PERIMETER} were (?:(?P<qualifier>{QUALIFIER}) ?)?\$(?P<value>{NUMBER}) ?billion"
    )
    TWELVE_MONTH: ClassVar[re.Pattern[str]] = re.compile(
        rf"(?:trailing twelve-month|full[- ]year \d{{4}}) revenues (?:reaching|of) "
        rf"(?:{QUALIFIER} ?)?\$({NUMBER}) billion"
    )
    GROWTH: ClassVar[re.Pattern[str]] = re.compile(
        r"year-on-year growth rate (?:was|increased[^.%]*?reaching) (\d{1,3})%"
        r"|represents (?:year-on-year )?growth of (\d{1,3})%"
        r"|represents (\d{1,3})% growth"
        rf"|\bup \${NUMBER} billion or (\d{{1,3}})% from"
        r"|\bup (\d{1,3})% from the (?:first|second|third|fourth) quarter"
        r"|\bthe (\d{1,3})% growth over Q[1-4]",
        re.IGNORECASE,
    )
    SHARES: ClassVar[re.Pattern[str]] = re.compile(
        r"\bQ[1-4](?:'s)? (?:their )?(?:worldwide )?market shares? (?:were|was|of) (?P<first>\d{1,2})%,? "
        r"(?:(?P<second>\d{1,2})%,? )?and (?P<third>\d{1,2})%"
    )
    PLAYER_SHARES: ClassVar[Dict[MarketPlayer, re.Pattern[str]]] = {
        MarketPlayer.AMAZON: re.compile(
            rf"\bAmazon[^.%]{{0,80}}?market share[^.%]{{0,80}}?\b(?:at|to|of) (?:(?P<qualifier>{QUALIFIER}) ?)?"
            r"(?P<low>\d{1,2})(?:-(?P<high>\d{1,2}))?%"
        ),
        MarketPlayer.MICROSOFT: re.compile(
            rf"\bMicrosoft[^.%]{{0,80}}?market share[^.%]{{0,100}}?\b(?:reaching|reached|to) "
            rf"(?:(?P<qualifier>{QUALIFIER}) ?)?(?P<low>\d{{1,2}})(?:-(?P<high>\d{{1,2}}))?%"
        ),
        MarketPlayer.GOOGLE: re.compile(
            rf"\bGoogle(?:'s)? (?:market )?share (?:stood at|was|nudged up to|reached) "
            rf"(?:(?P<qualifier>{QUALIFIER}) ?)?(?P<low>\d{{1,2}})(?:-(?P<high>\d{{1,2}}))?%"
        ),
    }
    BIG_THREE: ClassVar[re.Pattern[str]] = re.compile(
        rf"(?:In aggregate the three leaders accounted for|Amazon, Microsoft (?:and|&) Google (?:together accounted for"
        rf"|combined had an?)) "
        rf"(?:(?P<qualifier>{QUALIFIER}) ?)?(?P<low>\d{{1,2}})%"
    )
    PUBLIC_GROWTH: ClassVar[re.Pattern[str]] = re.compile(
        r"Public IaaS and PaaS services account for the bulk of[^.]*?grew by (\d{1,3})%"
    )
    PUBLIC_TOP_THREE: ClassVar[re.Pattern[str]] = re.compile(
        rf"top three (?:account for|control) (?:(?P<qualifier>{QUALIFIER}) ?)?(?P<low>\d{{1,2}})% of the market"
    )
    METHODOLOGY_BREAK: ClassVar[re.Pattern[str]] = re.compile(r"Relative to previous quarterly analyses")
    EUROPE_WORDING: ClassVar[re.Pattern[str]] = re.compile(r"European cloud (?:market|infrastructure service revenues)")
    EUROPE_MARKET: ClassVar[re.Pattern[str]] = re.compile(
        rf"European cloud market[^.]*?reaching (?:EUR |€)(?P<value>{NUMBER}) billion (?:\([^)]*\) )?in "
        r"(?:the (?P<quarter>first|second|third|fourth) quarter of )?(?P<year>\d{4})"
    )
    EUROPE_HALF: ClassVar[re.Pattern[str]] = re.compile(
        rf"European {PERIMETER} were (?:{QUALIFIER} ?)?(?:EUR |€)(?P<value>{NUMBER}) billion in the "
        r"(?P<half>first|second) half of (?P<year>\d{4})"
    )
    EUROPE_TWELVE_MONTH: ClassVar[re.Pattern[str]] = re.compile(
        rf"last four quarters European {PERIMETER} totaled (?:{QUALIFIER} ?)?(?:EUR |€)({NUMBER}) billion"
    )
    EUROPE_BIG_THREE: ClassVar[re.Pattern[str]] = re.compile(
        rf"three leading global cloud providers[^.%]*?account for (?:(?P<qualifier>{QUALIFIER}) ?)?(?P<low>\d{{1,2}})%"
    )
    EUROPE_PROVIDERS: ClassVar[re.Pattern[str]] = re.compile(
        rf"European (?:cloud |service )providers[^.]*?market share[^.]*?\bto (?:(?P<qualifier>{QUALIFIER}) ?)?"
        rf"(?P<low>\d{{1,2}})%(?:[^.]*?\bat (?:(?P<later_qualifier>{QUALIFIER}) ?)?(?P<later>\d{{1,2}})%)?"
    )
    EUROPE_LEADERS: ClassVar[re.Pattern[str]] = re.compile(
        r"Among the European cloud providers, (?P<names>[^.]*?) (?:is|are) the leaders?,? (?:each )?accounting for "
        r"(?P<low>\d{1,2})%"
    )
    RANK: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?i:(second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth))[- ](?i:placed|ranked) ([A-Z]\w+)"
    )

    name = "synergy"
    source: ClassVar[str] = "Synergy Research Group"
    catalogue_url: ClassVar[str] = ARTICLES_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (CDX_URL,)
    download_delay: float = 1.5

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.requested_slugs: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _slug(self, url: str) -> Optional[str]:
        """Get the slug of an article URL, whatever its scheme, port and query.

        Args:
            url (str): The URL, e.g. `http://www.srgresearch.com:80/articles/some-title?page=2`.

        Returns:
            Optional[str]: The lower case slug, e.g. `some-title`, `None` when the URL is not an article.
        """
        match = self.ARTICLE_PATH.fullmatch(urlparse(url).path)
        return match.group(1).casefold() if match else None

    def _article_request(self, slug: str) -> Optional[Request]:
        """Build the request of an article, once per slug.

        Args:
            slug (str): The article slug.

        Returns:
            Optional[Request]: The request of the live article, `None` when it was already requested.
        """
        if slug in self.requested_slugs:
            self.logger.debug("Not requesting the %s article %s again.", self.name, slug)
            return None
        self.requested_slugs.add(slug)
        return Request(f"{self.ARTICLES_URL}/{slug}")

    def _listing_requests(self, response: Response) -> Iterator[Request]:
        """Request the cloud market articles of the press releases page.

        Args:
            response (Response): The press releases page.

        Yields:
            Request: The request of each cloud market article not requested yet.

        Raises:
            CatalogueFormatError: If the page lists no article.
        """
        links = response.css("ul.bar-style li a.text-body")
        if not links:
            self.logger.error("The %s press releases page %s lists no article.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the press releases page lists no article")
        requested = 0
        for link in links:
            title = self._clean_text(link.get_all_text(separator=" ", strip=True))
            slug = self._slug(urljoin(response.url, link.attrib.get("href") or ""))
            if slug is None or not self.CLOUD_WORDING.search(title):
                self.logger.debug("Skipping the %s link %r, not a cloud market article.", self.name, title)
                continue
            if (request := self._article_request(slug)) is not None:
                requested += 1
                yield request
        self.logger.info(
            "%s press releases page %s: %d cloud market articles requested.", self.name, response.url, requested
        )

    def _archive_requests(self, response: Response) -> Iterator[Request]:
        """Request the older cloud market articles listed by the Wayback Machine, live on the website.

        Args:
            response (Response): The CDX response, a JSON array of rows whose first column is the archived URL.

        Yields:
            Request: The request of each cloud market article not requested yet.

        Raises:
            CatalogueFormatError: If the response is not a JSON array.
        """
        rows = self._json_body(response)
        if not isinstance(rows, list):
            self.logger.error("The %s Wayback Machine listing %s is not a JSON array.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the Wayback Machine listing is not a JSON array")
        requested = 0
        for row in rows:
            url = self._as_text(row[0]) if isinstance(row, list) and row else None
            slug = self._slug(url) if url else None
            if slug is None or not self.CLOUD_WORDING.search(slug.replace("-", " ")):
                continue
            if (request := self._article_request(slug)) is not None:
                requested += 1
                yield request
        self.logger.info(
            "%s Wayback Machine listing: %d archived URLs, %d older cloud market articles requested.",
            self.name,
            len(rows),
            requested,
        )

    def _article_text(self, article: Selector) -> str:
        """Read the text of an article body, without its title and the company boilerplate.

        Args:
            article (Selector): The article body (`div.article`).

        Returns:
            str: The text, with single spaces and plain quotes.
        """
        parts = article.xpath(
            ".//text()[not(ancestor::h2) and not(ancestor::script) and not(ancestor::style)"
            " and not(ancestor::*[@id='sales-info'])]"
        ).getall()
        text = " ".join(str(part) for part in parts)
        return self._clean_text(re.sub(r"[\u201c\u201d]", '"', re.sub(r"[\u2018\u2019]", "'", text)))

    def _published(self, text: str, response: Response) -> date:
        """Read the publication date of an article from its dateline.

        Args:
            text (str): The article text.
            response (Response): The article, for the logs.

        Returns:
            date: The publication date.

        Raises:
            CatalogueFormatError: If the article has no dateline, or an invalid date.
        """
        match = self.DATELINE.search(text)
        if match is None:
            self.logger.error("The %s article %s has no dateline.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the article has no `RENO, NV` dateline")
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").date()
        except ValueError as e:
            self.logger.error(
                "The %s article %s has an invalid date %r: %s", self.name, response.url, match.group(1), e
            )
            raise CatalogueFormatError(self.name, response.url, f"the date {match.group(1)!r} is invalid") from e

    def _quarter(self, published: date) -> str:
        """Get the quarter a release covers: the calendar quarter before its publication.

        Args:
            published (date): The publication date.

        Returns:
            str: The quarter, e.g. `2025Q4` for a release of February 2026.
        """
        quarter = (published.month - 1) // 3
        if quarter == 0:
            return f"{published.year - 1}Q4"
        return f"{published.year}Q{quarter}"

    def _check_quarter(self, period: str, response: Response) -> None:
        """Cross-check the quarter of a release with the alt text of its chart, e.g. `CIS Q226`.

        Args:
            period (str): The quarter inferred from the publication date.
            response (Response): The article.
        """
        for alt in response.css("div.article img::attr(alt)").getall():
            if (match := self.ALT_QUARTER.search(str(alt))) is None:
                continue
            charted = f"20{match.group(2)}Q{match.group(1)}"
            if charted != period:
                self.logger.warning(
                    "The %s article %s charts %s but was published after %s.", self.name, response.url, charted, period
                )
            return

    def _share(self, player: MarketPlayer, match: re.Match[str], part_of: Optional[MarketPlayer]) -> MarketShare:
        """Build a share from a matched figure: a value, or a band whose middle is the share.

        Args:
            player (MarketPlayer): The player.
            match (re.Match[str]): The figure, with the `low` group, and the optional `qualifier` and `high` groups.
            part_of (Optional[MarketPlayer]): The aggregate including the player, `None` for a top-level share.

        Returns:
            MarketShare: The share, approximate when it is qualified (e.g. "around 15%").
        """
        groups = match.groupdict()
        approximate = groups.get("qualifier") is not None
        low = float(match.group("low"))
        if groups.get("high") is None:
            return MarketShare(player=player, share_pct=low, approximate=approximate, part_of=part_of)
        low, high = sorted((low, float(match.group("high"))))
        return MarketShare(
            player=player,
            share_pct=(low + high) / 2,
            share_low_pct=low,
            share_high_pct=high,
            approximate=approximate,
            part_of=part_of,
        )

    def _plausible(self, shares: List[MarketShare], response: Response) -> bool:
        """Check the worldwide shares of Amazon, Microsoft and Google: in this order, and summing to a plausible total.

        Args:
            shares (List[MarketShare]): The shares, in the Amazon, Microsoft, Google order.
            response (Response): The article, for the logs.

        Returns:
            bool: Whether the shares are descending and their sum is in the plausible range (when all three are given).
        """
        values = [share.share_pct for share in shares]
        low, high = self.SHARE_TOTAL
        total = sum(values)
        if values == sorted(values, reverse=True) and total <= high and (len(values) < 3 or total >= low):
            return True
        self.logger.warning(
            "Dropping the implausible %s shares of %s: %s (sum %g%%).", self.name, response.url, values, total
        )
        return False

    def _world_shares(self, text: str, response: Response) -> List[MarketShare]:
        """Extract the worldwide shares: the big three combined, then Amazon, Microsoft and Google.

        Args:
            text (str): The article text.
            response (Response): The article, for the logs.

        Returns:
            List[MarketShare]: The shares. Amazon, Microsoft and Google are part of the big three when the combined
                share is given, and dropped when they are implausible.
        """
        big_three = self.BIG_THREE.search(text)
        part_of = MarketPlayer.BIG_THREE if big_three else None
        by_position: Dict[MarketPlayer, MarketShare] = {}
        if (listed := self.SHARES.search(text)) is not None:
            values = [value for value in listed.group("first", "second", "third") if value is not None]
            players = (MarketPlayer.AMAZON, MarketPlayer.MICROSOFT, MarketPlayer.GOOGLE)[-len(values) :]
            for player, value in zip(players, values, strict=True):
                by_position[player] = MarketShare(player=player, share_pct=float(value), part_of=part_of)
        shares: List[MarketShare] = []
        for player, pattern in self.PLAYER_SHARES.items():
            if player in by_position:
                shares.append(by_position[player])
            elif (match := pattern.search(text)) is not None:
                shares.append(self._share(player, match, part_of))
        if shares and not self._plausible(shares, response):
            shares = []
        if big_three is not None:
            shares.insert(0, self._share(MarketPlayer.BIG_THREE, big_three, None))
        return shares

    def _europe_shares(self, text: str) -> List[MarketShare]:
        """Extract the European shares: the three global leaders, the European providers and their leaders.

        Args:
            text (str): The article text.

        Returns:
            List[MarketShare]: The shares. SAP and Deutsche Telekom are part of the European providers when their
                combined share is given.
        """
        shares: List[MarketShare] = []
        if (big_three := self.EUROPE_BIG_THREE.search(text)) is not None:
            shares.append(self._share(MarketPlayer.BIG_THREE, big_three, None))
        part_of: Optional[MarketPlayer] = None
        if (providers := self.EUROPE_PROVIDERS.search(text)) is not None:
            part_of = MarketPlayer.EUROPEAN_PROVIDERS
            value, qualifier = providers.group("low", "qualifier")
            if providers.group("later") is not None:
                value, qualifier = providers.group("later", "later_qualifier")
            shares.append(MarketShare(player=part_of, share_pct=float(value), approximate=qualifier is not None))
        if (leaders := self.EUROPE_LEADERS.search(text)) is not None:
            for name in ("SAP", "Deutsche Telekom"):
                if re.search(rf"\b{name}\b", leaders.group("names")):
                    shares.append(self._share(self.NAMED_PLAYERS[name], leaders, part_of))
        return shares

    def _mentions(self, text: str, shares: List[MarketShare]) -> List[ProviderMention]:
        """Extract the providers named without a market share, in order of appearance, with their rank when given.

        Args:
            text (str): The article text.
            shares (List[MarketShare]): The shares of the report: their players are not mentioned.

        Returns:
            List[ProviderMention]: The mentions, e.g. `Alibaba` ranked 4 for "fourth-placed Alibaba".
        """
        shared = {share.player for share in shares}
        ranks = {name: self.ORDINALS[ordinal.casefold()] for ordinal, name in self.RANK.findall(text)}
        positions: Dict[str, int] = {}
        for name in (*self.KNOWN_PROVIDERS, *ranks):
            if (match := re.search(rf"\b{re.escape(name)}\b", text)) is not None:
                positions.setdefault(name, match.start())
        mentions: List[ProviderMention] = []
        for name in sorted(positions, key=positions.__getitem__):
            if self.NAMED_PLAYERS.get(name) in shared:
                self.logger.debug("Not mentioning %s, which has a market share.", name)
                continue
            mentions.append(ProviderMention(name=name, rank=ranks.get(name)))
        return mentions

    def _growth(self, text: str) -> Optional[float]:
        """Extract the year-on-year growth of the worldwide market, from its first statement.

        Args:
            text (str): The article text.

        Returns:
            Optional[float]: The growth, in percent, `None` when it is not stated in a known wording.
        """
        match = self.GROWTH.search(text)
        if match is None:
            return None
        return float(next(value for value in match.groups() if value is not None))

    def _report(
        self, fields: Dict[str, JsonValue], shares: List[MarketShare], mentions: List[ProviderMention]
    ) -> Iterator[MarketReport]:
        """Build a market report, if its figures are valid.

        Args:
            fields (Dict[str, JsonValue]): The report fields, but the shares and mentions.
            shares (List[MarketShare]): The shares.
            mentions (List[ProviderMention]): The mentions.

        Yields:
            MarketReport: The report, none (logged) when its figures are invalid.
        """
        try:
            report = MarketReport.model_validate({**fields, "shares": shares, "mentions": mentions})
        except ValidationError as e:
            self.logger.warning(
                "Skipping the invalid %s %s report of %s: %s", self.name, fields.get("period"), fields["source_url"], e
            )
            return
        yield report

    def _world_reports(self, text: str, fields: Dict[str, JsonValue], response: Response) -> Iterator[MarketReport]:
        """Extract the worldwide reports of a release: cloud infrastructure services, then public IaaS and PaaS.

        Args:
            text (str): The article text.
            fields (Dict[str, JsonValue]): The source fields of the reports (URL, title, publication date).
            response (Response): The article.

        Yields:
            MarketReport: Each valid report.
        """
        size = self.WORLD_SIZE.search(text)
        if size is None:
            return
        period = self._quarter(date.fromisoformat(str(fields["published"])))
        self._check_quarter(period, response)
        shares = self._world_shares(text, response)
        twelve_month = self.TWELVE_MONTH.search(text)
        world: Dict[str, JsonValue] = {
            **fields,
            "period": period,
            "region": MarketRegion.WORLDWIDE,
            "methodology_break": self.METHODOLOGY_BREAK.search(text) is not None,
        }
        yield from self._report(
            {
                **world,
                "segment": MarketSegment.CLOUD_INFRASTRUCTURE,
                "market_size_bn": float(size.group("value")),
                "twelve_month_bn": float(twelve_month.group(1)) if twelve_month else None,
                "growth_pct": self._growth(text),
            },
            shares,
            self._mentions(text, shares),
        )
        growth = self.PUBLIC_GROWTH.search(text)
        top_three = self.PUBLIC_TOP_THREE.search(text)
        if growth is None and top_three is None:
            return
        yield from self._report(
            {
                **world,
                "segment": MarketSegment.PUBLIC_IAAS_PAAS,
                "growth_pct": float(growth.group(1)) if growth else None,
            },
            [self._share(MarketPlayer.BIG_THREE, top_three, None)] if top_three else [],
            [],
        )

    def _europe_reports(self, text: str, fields: Dict[str, JsonValue]) -> Iterator[MarketReport]:
        """Extract the European reports of an article: the year or quarter of the shares, and the half-year if given.

        Args:
            text (str): The article text.
            fields (Dict[str, JsonValue]): The source fields of the reports (URL, title, publication date).

        Yields:
            MarketReport: Each valid report, in EUR. The shares and mentions go to the year or quarter report, or to
                the half-year report when the article gives no year or quarter.
        """
        if not self.EUROPE_WORDING.search(text):
            return
        shares = self._europe_shares(text)
        mentions = self._mentions(text, shares)
        europe: Dict[str, JsonValue] = {
            **fields,
            "region": MarketRegion.EUROPE,
            "segment": MarketSegment.CLOUD_INFRASTRUCTURE,
            "currency": "EUR",
        }
        if (market := self.EUROPE_MARKET.search(text)) is not None:
            quarter = market.group("quarter")
            twelve_month = self.EUROPE_TWELVE_MONTH.search(text)
            period = market.group("year") + (f"Q{self.ORDINALS[quarter]}" if quarter else "")
            yield from self._report(
                {
                    **europe,
                    "period": period,
                    "market_size_bn": float(market.group("value")),
                    "twelve_month_bn": float(twelve_month.group(1)) if twelve_month else None,
                },
                shares,
                mentions,
            )
            shares, mentions = [], []
        if (half := self.EUROPE_HALF.search(text)) is not None:
            period = f"{half.group('year')}H{self.ORDINALS[half.group('half')]}"
            yield from self._report(
                {**europe, "period": period, "market_size_bn": float(half.group("value"))}, shares, mentions
            )

    def _enriched(self, report: MarketReport) -> MarketReport:
        """Complete a report with the figures of the report of the same period, region and segment streamed before.

        Args:
            report (MarketReport): The extracted report.

        Returns:
            MarketReport: The report with the most shares, completed with the market size, growth and mentions the
                other one gives. The extracted report itself when none was streamed before.

        Notes:
            A quarter can be published by several articles, e.g. the quarterly release (with the growth) and a share
            trend article (with the big three combined share): the streamed report gathers both.
        """
        known = self.reports.get((report.period, report.region, report.segment))
        if known is None:
            return report
        primary, other = (report, known) if len(report.shares) >= len(known.shares) else (known, report)
        shared = {share.player for share in primary.shares}
        named = {mention.name for mention in primary.mentions}
        extra = [
            mention
            for mention in other.mentions
            if mention.name not in named and self.NAMED_PLAYERS.get(mention.name) not in shared
        ]
        return primary.model_copy(
            update={
                "market_size_bn": primary.market_size_bn or other.market_size_bn,
                "twelve_month_bn": primary.twelve_month_bn or other.twelve_month_bn,
                "growth_pct": primary.growth_pct if primary.growth_pct is not None else other.growth_pct,
                "mentions": [*primary.mentions, *extra],
                "methodology_break": primary.methodology_break or other.methodology_break,
            }
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_reports(self, response: Response) -> Iterator[MarketReport]:
        """Extract the market reports of an article.

        Args:
            response (Response): The article.

        Yields:
            MarketReport: Each report of the article (none when it is not a cloud market release), completed with
                the report of the same period, region and segment streamed before.

        Raises:
            CatalogueFormatError: If the page has no article body, or if a cloud market release has no valid dateline.
        """
        article = response.css("div.article").first
        if article is None:
            self.logger.error("The %s page %s has no article body.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the article body (`div.article`) is missing")
        text = self._article_text(article)
        if not self.WORLD_SIZE.search(text) and not self.EUROPE_WORDING.search(text):
            self.logger.debug("Skipping the %s article %s, it gives no cloud market figure.", self.name, response.url)
            return
        heading = article.css("h2").first
        title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
        fields: Dict[str, JsonValue] = {
            "source_url": response.url,
            "title": title or response.url,
            "published": self._published(text, response).isoformat(),
        }
        for report in (*self._world_reports(text, fields, response), *self._europe_reports(text, fields)):
            if int(report.period[:4]) < self.FIRST_YEAR:
                self.logger.debug(
                    "Skipping the %s %s report of %s, before %d.",
                    self.name,
                    report.period,
                    response.url,
                    self.FIRST_YEAR,
                )
                continue
            yield self._enriched(report)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the articles of the press releases page or of the Wayback Machine listing, or read an article.

        Args:
            response (Response): The press releases page, the Wayback Machine listing or an article.

        Yields:
            Union[Dict[str, JsonValue], Request]: The article requests, or each new or more complete market report.

        Raises:
            CatalogueFormatError: If the press releases page lists no article, if the Wayback Machine listing is not a
                JSON array, or if an article cannot be read.
        """
        link = urlparse(response.url)
        if link.netloc == urlparse(self.CDX_URL).netloc:
            for request in self._archive_requests(response):
                yield request
            return
        if link.path.rstrip("/") == urlparse(self.ARTICLES_URL).path:
            for request in self._listing_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
