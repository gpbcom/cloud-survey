from __future__ import annotations

# Standard Library Imports.
import html
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.volcengine.enums import (
    VolcanoEngineDocField,
    VolcanoEngineDocStage,
    VolcanoEnginePeriod,
    VolcanoEnginePriceAction,
    VolcanoEnginePriceField,
    VolcanoEngineUnit,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class VolcanoEngineCrawler(BaseCloudCrawler):
    """Volcano Engine (火山引擎) catalogue crawler.

    Attributes:
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product card links, waited for in the browser.
        PRODUCT_HOST (ClassVar[str]): The host of the product pages.
        PRODUCT_PATH (ClassVar[str]): The path prefix of the product pages.
        CATEGORY_BLOCKS (ClassVar[str]): The CSS selector of the category blocks (one per tab, in both copies).
        CATEGORY_TITLE (ClassVar[str]): The CSS selector of the category title of a block.
        SUB_CATEGORIES (ClassVar[str]): The CSS selector of the sub-category groups of a block.
        SUB_CATEGORY_TITLE (ClassVar[str]): The CSS selector of the sub-category title of a group.
        PRICES_URL (ClassVar[str]): An action of the anonymous price API of the pricing page (POST, no key).
        NAVIGATION_URL (ClassVar[str]): Its navigation, the source of every price.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices (yuan, not stated by the API).
        DETAILS_TEMPLATE (ClassVar[int]): The type of the price detail templates (2 being the calculators).
        CONFIGURATION_UNITS (ClassVar[Dict[Tuple[VolcanoEngineUnit, str], PriceUnit]]): The unit of a charge item
            billed by its configuration over time, by its unit and period.
        USAGE_UNITS (ClassVar[Dict[VolcanoEngineUnit, Tuple[PriceUnit, Decimal]]]): The unit of a charge item
            billed by its usage, and the normalized units in one.
        USAGE_ONLY (ClassVar[FrozenSet[VolcanoEngineUnit]]): The units of a charge item always billed by usage.
        TERMS (ClassVar[Dict[int, PriceTerm]]): The term of a subscription, by its months.
        GLOBAL_REGION (ClassVar[str]): The region of a charge item without region.
        ACTION_META (ClassVar[str]): The request meta holding the action of a call.
        TEMPLATE_META (ClassVar[str]): The request meta holding the template code.
        PRODUCT_NAME_META (ClassVar[str]): The request meta holding the product name.
        CATEGORY_META (ClassVar[str]): The request meta holding the product category.
        DOCS_HOME_URL (ClassVar[str]): The documentation home, listing the documentation libraries by title.
        DOCS_LIBRARY_URL (ClassVar[str]): A documentation library, its document tree in the page.
        DOCS_DETAIL_URL (ClassVar[str]): The documentation API giving a document (no key).
        DOCS_PAGE_URL (ClassVar[str]): The public page of a document, the source of its prices.
        DOCS_LIBRARY (ClassVar[re.Pattern[str]]): A library of the documentation home: its title and code.
        DOCS_TREE (ClassVar[re.Pattern[str]]): A document of a library tree: its code, library and title.
        PRICE_DOC_TITLE (ClassVar[re.Pattern[str]]): The title words of a document holding prices.
        NOT_PRICE_DOC_TITLE (ClassVar[re.Pattern[str]]): The title words of a billing document without price list
            (announcements, examples, arrears, refunds).
        MD_ROW (ClassVar[re.Pattern[str]]): A Markdown table row, its cells between pipes.
        MD_SEPARATOR (ClassVar[re.Pattern[str]]): The separator row under a Markdown table header.
        MD_TAG (ClassVar[re.Pattern[str]]): An HTML tag or component tag of the Markdown, e.g. `<br>`, `<Tab>`.
        DOCS_STAGE_META (ClassVar[str]): The request meta holding the stage of a documentation request.
        DOCS_PRODUCT_META (ClassVar[str]): The request meta holding the catalogue product of a documentation.
        DOCS_LIBRARY_META (ClassVar[str]): The request meta holding the documentation library code.
        DOCS_PAGE_META (ClassVar[str]): The request meta holding the public page of a document.
        price_pending (int): The API calls not answered yet, in price mode.
        price_rows (int): The prices read, in price mode.
        price_templates (Dict[str, Dict[str, Dict[str, JsonValue]]]): The charge items of each template read, by
            template code, until its prices are read.

    Notes:
        The only source is the product cards of the https://www.volcengine.com/product/list page, rendered by
        JavaScript (the crawler waits for the cards). Their class names end with a generated suffix, e.g.
        `product-card-f4_h`, so they are matched by prefix. Each card is in the page twice. The cards linking to the
        console, the API explorer, the SDKs or the documentation are not products. The query strings (`utm_*`
        tracking, disallowed by robots.txt) are removed from the links. The names and descriptions are in Chinese.
        The cards are grouped by category (e.g. `计算`) and sub-category (e.g. `弹性计算`): a product gets the labels
        of every group it is listed in.
        In price mode it reads the anonymous price API of the pricing page: its navigation lists the products and
        their price templates. Each template definition gives the unit and name of its charge items, then its
        price table gives their prices, in yuan, hourly or by subscription of 1 to 36 months (per month, its
        factor being its months), a progressive price expanding into its tiers. The navigation is one source,
        recorded once every call is answered.
        The products absent from that API are often priced in their documentation: the documentation home lists
        the libraries by title, a library whose title is a catalogue product name (spaces and case ignored) or
        whose code is the slug of its page is read, and its billing documents (`计费`, `价格`, `定价` titles
        but not announcements or examples) are read through the documentation API as Markdown. Their tables are
        read by the generic table reader, a merged cell (left empty in Markdown) taking the cell above.
    """

    PRODUCT_CARDS: ClassVar[str] = 'div[class*="product-card-"] > a'
    PRODUCT_HOST: ClassVar[str] = "www.volcengine.com"
    PRODUCT_PATH: ClassVar[str] = "/product/"
    CATEGORY_BLOCKS: ClassVar[str] = 'div[class^="block-"]'
    CATEGORY_TITLE: ClassVar[str] = '[class*="tabs-title-"]'
    SUB_CATEGORIES: ClassVar[str] = 'div[class^="secondLevel"]:not([class*="secondLevel-title"])'
    SUB_CATEGORY_TITLE: ClassVar[str] = '[class*="secondLevel-title"]'

    name = "volcengine"
    catalogue_url: ClassVar[str] = "https://www.volcengine.com/product/list"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("火山引擎", "Volcano Engine ")
    PRICES_URL: ClassVar[str] = (
        "https://www.volcengine.com/anonymous-api/trade/price?Action={action}&Version=2020-01-01"
    )
    NAVIGATION_URL: ClassVar[str] = PRICES_URL.format(action=VolcanoEnginePriceAction.NAVIGATION.value)
    PRICE_CURRENCY: ClassVar[str] = "CNY"
    DETAILS_TEMPLATE: ClassVar[int] = 1
    CONFIGURATION_UNITS: ClassVar[Dict[Tuple[VolcanoEngineUnit, str], PriceUnit]] = {
        (VolcanoEngineUnit.MACHINE, VolcanoEnginePeriod.HOURLY): PriceUnit.HOUR,
        (VolcanoEngineUnit.MACHINE, VolcanoEnginePeriod.MONTHLY): PriceUnit.MONTH,
        (VolcanoEngineUnit.PIECE, VolcanoEnginePeriod.HOURLY): PriceUnit.UNIT_HOUR,
        (VolcanoEngineUnit.PIECE, VolcanoEnginePeriod.MONTHLY): PriceUnit.UNIT_MONTH,
        (VolcanoEngineUnit.VCPU, VolcanoEnginePeriod.HOURLY): PriceUnit.VCPU_HOUR,
        (VolcanoEngineUnit.VCPU, VolcanoEnginePeriod.MONTHLY): PriceUnit.UNIT_MONTH,
        (VolcanoEngineUnit.GIB, VolcanoEnginePeriod.HOURLY): PriceUnit.GIB_HOUR,
        (VolcanoEngineUnit.GIB, VolcanoEnginePeriod.MONTHLY): PriceUnit.GIB_MONTH,
        (VolcanoEngineUnit.GB, VolcanoEnginePeriod.HOURLY): PriceUnit.GIB_HOUR,
        (VolcanoEngineUnit.GB, VolcanoEnginePeriod.MONTHLY): PriceUnit.GIB_MONTH,
        (VolcanoEngineUnit.NODE, VolcanoEnginePeriod.HOURLY): PriceUnit.HOUR,
        (VolcanoEngineUnit.NODE, VolcanoEnginePeriod.MONTHLY): PriceUnit.MONTH,
        (VolcanoEngineUnit.COMPUTE_UNIT, VolcanoEnginePeriod.HOURLY): PriceUnit.UNIT_HOUR,
        (VolcanoEngineUnit.COMPUTE_UNIT, VolcanoEnginePeriod.MONTHLY): PriceUnit.UNIT_MONTH,
        (VolcanoEngineUnit.MBPS, VolcanoEnginePeriod.HOURLY): PriceUnit.UNIT_HOUR,
        (VolcanoEngineUnit.MBPS, VolcanoEnginePeriod.MONTHLY): PriceUnit.UNIT_MONTH,
    }
    USAGE_UNITS: ClassVar[Dict[VolcanoEngineUnit, Tuple[PriceUnit, Decimal]]] = {
        VolcanoEngineUnit.GIB: (PriceUnit.GIB, Decimal(1)),
        VolcanoEngineUnit.GB: (PriceUnit.GIB, Decimal(1)),
        VolcanoEngineUnit.TIMES: (PriceUnit.REQUEST, Decimal(1)),
        VolcanoEngineUnit.TEN_THOUSAND_TIMES: (PriceUnit.REQUEST, Decimal(10_000)),
        VolcanoEngineUnit.THOUSAND_TOKENS: (PriceUnit.TOKEN, Decimal(1000)),
        VolcanoEngineUnit.MILLION_TOKENS: (PriceUnit.TOKEN, Decimal(1_000_000)),
        VolcanoEngineUnit.TOKENS: (PriceUnit.TOKEN, Decimal(1)),
        VolcanoEngineUnit.MACHINE: (PriceUnit.UNIT, Decimal(1)),
        VolcanoEngineUnit.PIECE: (PriceUnit.UNIT, Decimal(1)),
        VolcanoEngineUnit.MACHINE_HOURS: (PriceUnit.HOUR, Decimal(1)),
        VolcanoEngineUnit.HOURS: (PriceUnit.HOUR, Decimal(1)),
        VolcanoEngineUnit.MINUTES: (PriceUnit.MINUTE, Decimal(1)),
        VolcanoEngineUnit.ENTRIES: (PriceUnit.REQUEST, Decimal(1)),
        VolcanoEngineUnit.MILLION_SAMPLES: (PriceUnit.REQUEST, Decimal(1_000_000)),
        VolcanoEngineUnit.MILLION_ENTRIES: (PriceUnit.REQUEST, Decimal(1_000_000)),
        VolcanoEngineUnit.CHARACTERS: (PriceUnit.CHARACTER, Decimal(1)),
        VolcanoEngineUnit.THOUSAND_TOKENS_SPACED: (PriceUnit.TOKEN, Decimal(1000)),
        VolcanoEngineUnit.SHEETS: (PriceUnit.IMAGE, Decimal(1)),
        VolcanoEngineUnit.NODE: (PriceUnit.UNIT, Decimal(1)),
        VolcanoEngineUnit.COMPUTE_UNIT: (PriceUnit.UNIT, Decimal(1)),
    }
    USAGE_ONLY: ClassVar[FrozenSet[VolcanoEngineUnit]] = frozenset(
        {
            VolcanoEngineUnit.TIMES,
            VolcanoEngineUnit.TEN_THOUSAND_TIMES,
            VolcanoEngineUnit.THOUSAND_TOKENS,
            VolcanoEngineUnit.MILLION_TOKENS,
            VolcanoEngineUnit.TOKENS,
            VolcanoEngineUnit.MACHINE_HOURS,
            VolcanoEngineUnit.HOURS,
            VolcanoEngineUnit.MINUTES,
            VolcanoEngineUnit.ENTRIES,
            VolcanoEngineUnit.MILLION_SAMPLES,
            VolcanoEngineUnit.MILLION_ENTRIES,
            VolcanoEngineUnit.CHARACTERS,
            VolcanoEngineUnit.THOUSAND_TOKENS_SPACED,
            VolcanoEngineUnit.SHEETS,
        }
    )
    TERMS: ClassVar[Dict[int, PriceTerm]] = {
        1: PriceTerm.MONTH,
        3: PriceTerm.THREE_MONTHS,
        6: PriceTerm.SIX_MONTHS,
        12: PriceTerm.ONE_YEAR,
        24: PriceTerm.TWO_YEARS,
        36: PriceTerm.THREE_YEARS,
        48: PriceTerm.FOUR_YEARS,
        60: PriceTerm.FIVE_YEARS,
    }
    GLOBAL_REGION: ClassVar[str] = "global"
    ACTION_META: ClassVar[str] = "price_action"
    TEMPLATE_META: ClassVar[str] = "price_template"
    PRODUCT_NAME_META: ClassVar[str] = "price_product"
    CATEGORY_META: ClassVar[str] = "price_category"
    DOCS_HOME_URL: ClassVar[str] = "https://docs.volcengine.com/docs?lang=zh"
    DOCS_LIBRARY_URL: ClassVar[str] = "https://docs.volcengine.com/docs/{library}?lang=zh"
    DOCS_DETAIL_URL: ClassVar[str] = (
        "https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode={library}&DocumentCode={document}"
        "&type=online&Lang=zh"
    )
    DOCS_PAGE_URL: ClassVar[str] = "https://docs.volcengine.com/docs/{library}/{document}"
    DOCS_LIBRARY: ClassVar[re.Pattern[str]] = re.compile(
        r'\{"title":"(?P<title>[^"]+)","description":"[^"]*","href":"[^"]*",'
        r'"slugHref":"(?:\\u002F|/)docs(?:\\u002F|/)(?P<library>[\w.-]+)"\}'
    )
    DOCS_TREE: ClassVar[re.Pattern[str]] = re.compile(
        r'"DocumentCode":"(?P<document>[^"]+)","LibraryCode":"(?P<library>[^"]+)",'
        r'"ParentCode":"[^"]*","Title":"(?P<title>[^"]*)"'
    )
    PRICE_DOC_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"计费|价格|定价|收费|单价|资源包")
    NOT_PRICE_DOC_TITLE: ClassVar[re.Pattern[str]] = re.compile(
        r"公告|示例|欠费|退订|退费|续费|账单|变更|转换|常见问题|FAQ|到期|停服|停止", re.I
    )
    MD_ROW: ClassVar[re.Pattern[str]] = re.compile(r"^\|(?P<cells>.*)\|$")
    MD_SEPARATOR: ClassVar[re.Pattern[str]] = re.compile(r"^\|?\s*:?-{2,}")
    MD_TAG: ClassVar[re.Pattern[str]] = re.compile(r"<[^>]+>")
    DOCS_STAGE_META: ClassVar[str] = "price_docs_stage"
    DOCS_PRODUCT_META: ClassVar[str] = "price_docs_product"
    DOCS_LIBRARY_META: ClassVar[str] = "price_docs_library"
    DOCS_PAGE_META: ClassVar[str] = "price_docs_page"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_pending = 0
        self.price_rows = 0
        self.price_templates: Dict[str, Dict[str, Dict[str, JsonValue]]] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _product_url(self, response: Response, href: str) -> Optional[str]:
        """Get the product page of a card link, without query string nor fragment.

        Args:
            response (Response): The catalogue page, the links being relative to it.
            href (str): The card link.

        Returns:
            Optional[str]: The absolute product page URL, `None` when the link is missing or is not a product page.
        """
        link = urlparse(urljoin(response.url, href.strip()))
        if not href.strip() or link.netloc != self.PRODUCT_HOST or not link.path.startswith(self.PRODUCT_PATH):
            return None
        return link._replace(query="", fragment="").geturl()

    def _title(self, element: Selector, selector: str) -> str:
        """Read the text of the first element matching a CSS selector within an element.

        Args:
            element (Selector): The element.
            selector (str): The CSS selector.

        Returns:
            str: The text, empty when no element matches.
        """
        match = element.css(selector).first
        return self._clean_text(match.get_all_text(separator=" ", strip=True)) if match is not None else ""

    def _card_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the category and sub-category labels of the product cards, by product page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Dict[str, List[str]]: The labels of each product page (as cleaned by `_product_url`), in page order.
        """
        categories: Dict[str, List[str]] = {}
        for block in response.css(self.CATEGORY_BLOCKS):
            category = self._title(block, self.CATEGORY_TITLE)
            for group in block.css(self.SUB_CATEGORIES):
                labels = [category, self._title(group, self.SUB_CATEGORY_TITLE)]
                for card in group.css(self.PRODUCT_CARDS):
                    if url := self._product_url(response, card.attrib.get(HtmlAttribute.HREF, "")):
                        categories.setdefault(url, []).extend(labels)
        self.logger.debug("%d categorized product pages in %s.", len(categories), response.url)
        return categories

    def _card_product(
        self, response: Response, card: Selector, categories: Dict[str, List[str]]
    ) -> Optional[CloudProduct]:
        """Extract the product of a card: its title without the tags (e.g. `公测中`) and its description.

        Args:
            response (Response): The catalogue page.
            card (Selector): The card link.
            categories (Dict[str, List[str]]): The category labels of each product page.

        Returns:
            Optional[CloudProduct]: The product, `None` when the card is not a valid product.
        """
        title = card.css('[class*="product-title-"]').first
        description = card.css('[class*="product-description-"]').first
        name = self._clean_text(title.text) if title is not None else ""
        href = card.attrib.get(HtmlAttribute.HREF, "")
        url = self._product_url(response, href)
        if url is None:
            self.logger.debug("Skipping the card %r, %s is not a product page.", name, href)
            return None
        text = description.get_all_text(separator=" ", strip=True) if description is not None else None
        return self._build_product(name, text, url, categories=categories.get(url, []))

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue cards.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, every card being in the page twice.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._card_categories(response)
        for card in cards:
            if product := self._card_product(response, card, categories):
                yield product

    async def _catalogue_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the catalogue page, waiting for its product cards to be rendered.

        Yields:
            Request: The catalogue page request.
        """
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield Request(
            self.catalogue_url, priority=self.PRIMARY_PRIORITY, wait_selector=self.PRODUCT_CARDS, network_idle=True
        )

    def _api_url(self, action: VolcanoEnginePriceAction) -> str:
        """Build the URL of an action of the anonymous price API.

        Args:
            action (VolcanoEnginePriceAction): The action.

        Returns:
            str: Its URL.
        """
        return self.PRICES_URL.format(action=action.value)

    def _api_result(self, response: Response) -> Dict[str, JsonValue]:
        """Read the result of a call to the anonymous price API.

        Args:
            response (Response): The response.

        Returns:
            Dict[str, JsonValue]: Its result.

        Raises:
            CatalogueFormatError: If it has no result.
        """
        data = self._json_body(response)
        result = data.get(VolcanoEnginePriceField.RESULT) if isinstance(data, dict) else None
        if not isinstance(result, dict):
            self.logger.error("The Volcano Engine price API answered %s without result.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price API answered without result")
        return result

    def _leaf_products(self, nodes: JsonValue, category: str) -> Iterator[Tuple[Dict[str, JsonValue], str]]:
        """Walk the price navigation down to its products.

        Args:
            nodes (JsonValue): The nodes of a level of the navigation.
            category (str): The category of the level (the top level name).

        Yields:
            Tuple[Dict[str, JsonValue], str]: Each product and its category.
        """
        for node in nodes if isinstance(nodes, list) else []:
            if not isinstance(node, dict):
                continue
            if isinstance(node.get(VolcanoEnginePriceField.TEMPLATE_INFO_LIST), list):
                yield node, category
            name = node.get(VolcanoEnginePriceField.NAME)
            yield from self._leaf_products(
                node.get(VolcanoEnginePriceField.CHILDREN), category or (name if isinstance(name, str) else "")
            )

    def _charge_items(self, value: JsonValue, found: Dict[str, Dict[str, JsonValue]]) -> None:
        """Gather the charge items of a template definition (those naming their unit), wherever they are.

        Args:
            value (JsonValue): A part of the template definition.
            found (Dict[str, Dict[str, JsonValue]]): The charge items found, by charge item code (completed).
        """
        if isinstance(value, dict):
            code = value.get(VolcanoEnginePriceField.CHARGE_ITEM_CODE)
            if isinstance(code, str) and VolcanoEnginePriceField.UNIT in value:
                found[code] = value
            for child in value.values():
                self._charge_items(child, found)
        elif isinstance(value, list):
            for child in value:
                self._charge_items(child, found)

    def _charge_unit(self, item: Dict[str, JsonValue], period: str, times: int) -> Tuple[PriceUnit, Decimal, str]:
        """Normalize what a price of a charge item is per.

        Args:
            item (Dict[str, JsonValue]): The charge item (its unit and whether billed by usage).
            period (str): The period of the price (`hourly`, `monthly`).
            times (int): The periods it is for.

        Returns:
            Tuple[PriceUnit, Decimal, str]: The unit, the normalized units in one (the months of a subscription, a
                count of calls or tokens) and the unit as written, other when unknown.
        """
        written = str(item.get(VolcanoEnginePriceField.UNIT) or "").strip()
        try:
            unit = VolcanoEngineUnit(written if written in tuple(VolcanoEngineUnit) else written.lower())
        except ValueError:
            self.logger.debug("The Volcano Engine unit %r has no known unit: kept as other.", written)
            return PriceUnit.OTHER, Decimal(times), f"{written}/{period}"
        usage = item.get(VolcanoEnginePriceField.BILLING_BY_USAGE) is True or unit in self.USAGE_ONLY
        if usage:
            normalized, factor = self.USAGE_UNITS.get(unit, (PriceUnit.OTHER, Decimal(1)))
            return normalized, factor, written
        configured = self.CONFIGURATION_UNITS.get((unit, period))
        if configured is None:
            return PriceUnit.OTHER, Decimal(times), f"{written}/{period}"
        return configured, Decimal(times), f"{written}/{period}"

    def _row_prices(
        self, row: Dict[str, JsonValue], items: Dict[str, Dict[str, JsonValue]], meta: Dict[str, JsonValue]
    ) -> Iterator[ServicePrice]:
        """Read the prices of a row of a price table.

        Args:
            row (Dict[str, JsonValue]): The row.
            items (Dict[str, Dict[str, JsonValue]]): The charge items of the template, by code.
            meta (Dict[str, JsonValue]): The request meta (the product and its category).

        Yields:
            ServicePrice: One price per period (hourly, monthly subscriptions of 1 to 36 months), a progressive
                price expanding into its tiers.
        """
        code = row.get(VolcanoEnginePriceField.CHARGE_ITEM_CODE)
        if not isinstance(code, str):
            return
        item = items.get(code, {})
        region = item.get(VolcanoEnginePriceField.REGION)
        configuration = row.get(VolcanoEnginePriceField.CONFIGURATION_CODE)
        prices = row.get(VolcanoEnginePriceField.PRICE_INFO_LIST)
        for entry in prices if isinstance(prices, list) else []:
            if not isinstance(entry, dict):
                continue
            period = str(entry.get(VolcanoEnginePriceField.PERIOD) or "")
            times = entry.get(VolcanoEnginePriceField.TIMES)
            times = times if isinstance(times, int) and times > 0 else 1
            unit, factor, written = self._charge_unit(item, period, times)
            subscription = period == VolcanoEnginePeriod.MONTHLY
            base: Dict[str, RawValue] = {
                "service": meta.get(self.PRODUCT_NAME_META),
                "family": meta.get(self.CATEGORY_META) or None,
                "region": region if isinstance(region, str) and region else self.GLOBAL_REGION,
                "instance_type": configuration if unit in (PriceUnit.HOUR, PriceUnit.MONTH) else None,
                "attributes": {
                    field.value: item.get(field)
                    for field in (VolcanoEnginePriceField.CONFIGURATION_NAME, VolcanoEnginePriceField.DISPLAY_NAME)
                    if item.get(field)
                },
                "unit": unit,
                "unit_raw": written,
                "unit_factor": factor,
                "currency": self.PRICE_CURRENCY,
                "term": self.TERMS.get(times, PriceTerm.NONE) if subscription else PriceTerm.NONE,
                "source_url": self.NAVIGATION_URL,
                "source_kind": PriceSourceKind.API,
            }
            key = f"{code}/{configuration}/{period}/{times}"
            bounds = str(entry.get(VolcanoEnginePriceField.MEASURE_INTERVAL) or "")
            amounts = str(entry.get(VolcanoEnginePriceField.PRICE_INTERVAL) or "")
            tiers = (
                list(zip(bounds.split(","), amounts.split(","), strict=False))
                if bounds and amounts
                else [("0", str(entry.get(VolcanoEnginePriceField.PRICE)))]
            )
            for index, (start, amount) in enumerate(tiers):
                try:
                    price = Decimal(amount)
                except ArithmeticError:
                    self.logger.debug("A Volcano Engine price of %s is unreadable: %r.", code, amount)
                    continue
                end = tiers[index + 1][0] if index + 1 < len(tiers) else None
                fact = self._price_fact(
                    {
                        **base,
                        "sku_key": f"{key}/{index}" if len(tiers) > 1 else key,
                        "price": price,
                        "model": (
                            PriceModel.FREE
                            if price == 0
                            else PriceModel.COMMITMENT
                            if subscription
                            else PriceModel.ON_DEMAND
                        ),
                        "tier_start": start or "0",
                        "tier_end": end,
                    }
                )
                if fact is not None:
                    yield fact

    def _markdown_page(self, markdown: str) -> str:
        """Turn the Markdown of a document into an HTML page for the generic table reader.

        Args:
            markdown (str): The Markdown, its tables written with pipes.

        Returns:
            str: The page: each table as a `<table>`, each other text line as a paragraph (the table context).

        Notes:
            A Markdown table has no merged cell: the cells of a merged column are left empty below the first.
            Each leading empty cell of a row takes the cell above, as a row span would.
        """
        parts: List[str] = []
        table: List[List[str]] = []
        for raw in [*markdown.splitlines(), ""]:
            line = raw.strip()
            found = self.MD_ROW.match(line)
            if found is not None and not self.MD_SEPARATOR.match(line):
                row = [self._clean_text(self.MD_TAG.sub(" ", cell)) for cell in found.group("cells").split("|")]
                above = table[-1] if len(table) > 1 else []
                for index, cell in enumerate(row):
                    if cell or index >= len(above):
                        break
                    row[index] = above[index]
                table.append(row)
                continue
            if found is not None:
                continue
            if table:
                cells = "".join(f"<tr>{''.join(f'<td>{html.escape(cell)}</td>' for cell in row)}</tr>" for row in table)
                parts.append(f"<table>{cells}</table>")
                table = []
            text = self._clean_text(self.MD_TAG.sub(" ", line)).lstrip("#*> ").strip()
            if text:
                parts.append(f"<p>{html.escape(text)}</p>")
        self.logger.debug("Volcano Engine document turned into %d page parts.", len(parts))
        return f"<html><body>{''.join(parts)}</body></html>"

    def _doc_libraries(self, response: Response) -> Iterator[Request]:
        """Request the documentation libraries of the catalogue products, from the documentation home.

        Args:
            response (Response): The documentation home.

        Yields:
            Request: One request per library titled as a live catalogue product (spaces and case ignored) or coded
                as the slug of its page.
        """
        text = response.body.decode("utf-8", errors="replace")
        by_title: Dict[str, str] = {}
        by_code: Dict[str, str] = {}
        for found in self.DOCS_LIBRARY.finditer(text):
            library = found.group("library")
            by_title.setdefault(re.sub(r"\s+", "", found.group("title")).casefold(), library)
            by_code.setdefault(library.casefold(), library)
        requested: Set[str] = set()
        for name, url in self.price_products.items():
            slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].casefold() if url else ""
            library = by_title.get(re.sub(r"\s+", "", name).casefold()) or by_code.get(slug)
            if library is None or library in requested:
                continue
            requested.add(library)
            yield self._price_request(
                self.DOCS_LIBRARY_URL.format(library=library),
                {
                    self.DOCS_STAGE_META: VolcanoEngineDocStage.LIBRARY.value,
                    self.DOCS_PRODUCT_META: name,
                    self.DOCS_LIBRARY_META: library,
                },
            )
        if not by_title:
            self.logger.warning("The Volcano Engine documentation home %s lists no library.", response.url)
        self.logger.info(
            "%d Volcano Engine documentation libraries of %d listed match a catalogue product.",
            len(requested),
            len(by_title),
        )

    def _price_docs(self, response: Response) -> Iterator[Request]:
        """Request the billing documents of a documentation library.

        Args:
            response (Response): The library page, its document tree in its state.

        Yields:
            Request: One documentation API call per billing document of the library, once each.
        """
        library = str(response.meta.get(self.DOCS_LIBRARY_META) or "")
        product = str(response.meta.get(self.DOCS_PRODUCT_META) or "")
        documents: Set[str] = set()
        for found in self.DOCS_TREE.finditer(response.body.decode("utf-8", errors="replace")):
            title = found.group("title")
            document = found.group("document")
            if found.group("library") != library or document in documents:
                continue
            if not self.PRICE_DOC_TITLE.search(title) or self.NOT_PRICE_DOC_TITLE.search(title):
                continue
            documents.add(document)
            yield self._price_request(
                self.DOCS_DETAIL_URL.format(library=library, document=document),
                {
                    self.DOCS_STAGE_META: VolcanoEngineDocStage.DOCUMENT.value,
                    self.DOCS_PRODUCT_META: product,
                    self.DOCS_PAGE_META: self.DOCS_PAGE_URL.format(library=library, document=document),
                },
            )
        if not documents:
            self.logger.warning(
                "The Volcano Engine documentation of %s (%s) has no billing document.", product, library
            )
        self.logger.info("%d billing documents of %s (%s) to read.", len(documents), product, library)

    def _doc_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the price tables of a billing document, given by the documentation API as Markdown.

        Args:
            response (Response): The documentation API answer.

        Yields:
            ServicePrice: The prices of its tables, named after the catalogue product of the library.

        Raises:
            CatalogueFormatError: If the answer has no Markdown document (a folder of the tree, answered without
                result nor error, has no price).
        """
        data = self._json_body(response)
        result = data.get(VolcanoEngineDocField.RESULT) if isinstance(data, dict) else None
        metadata = data.get(VolcanoEngineDocField.METADATA) if isinstance(data, dict) else None
        if result is None and isinstance(metadata, dict) and VolcanoEngineDocField.ERROR not in metadata:
            self.logger.info("The Volcano Engine document %s is a folder of the tree: no price.", response.url)
            return
        markdown = result.get(VolcanoEngineDocField.MD_CONTENT) if isinstance(result, dict) else None
        if not isinstance(markdown, str):
            self.logger.error("The Volcano Engine documentation API answered %s without document.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the documentation API answered without document")
        page_url = str(response.meta.get(self.DOCS_PAGE_META) or response.url)
        page = Response(
            url=page_url,
            content=self._markdown_page(markdown).encode("utf-8"),
            status=200,
            reason="OK",
            cookies={},
            headers={},
            request_headers={},
            meta={self.PRODUCT_PAGE_META: str(response.meta.get(self.DOCS_PRODUCT_META) or "")},
        )
        prices = list(self._product_page_prices(page))
        self._record_price_source(page_url, len(prices))
        self.logger.info("Volcano Engine billing document %s read: %d prices.", page_url, len(prices))
        yield from prices

    def _docs_facts(self, response: Response) -> Iterator[PriceFact]:
        """Read a documentation request: the home, a library or a billing document.

        Args:
            response (Response): The answer.

        Yields:
            PriceFact: The library requests of the home, the document requests of a library, or the prices of a
                document.
        """
        match response.meta.get(self.DOCS_STAGE_META):
            case VolcanoEngineDocStage.HOME:
                yield from self._doc_libraries(response)
            case VolcanoEngineDocStage.LIBRARY:
                yield from self._price_docs(response)
            case VolcanoEngineDocStage.DOCUMENT:
                yield from self._doc_prices(response)
            case stage:
                self.logger.warning("Unknown Volcano Engine documentation stage %r of %s.", stage, response.url)

    def _price_settled(self) -> None:
        """Count an API call as answered, and record the navigation once every call is answered."""
        self.price_pending -= 1
        if self.price_pending == 0 and not self.price_failures:
            self._record_price_source(self.NAVIGATION_URL, self.price_rows)
            self.logger.info("The Volcano Engine prices are read whole: %d prices.", self.price_rows)

    def _api_request(
        self, action: VolcanoEnginePriceAction, body: Dict[str, JsonValue], meta: Dict[str, JsonValue]
    ) -> Request:
        """Build a counted call to the anonymous price API.

        Args:
            action (VolcanoEnginePriceAction): The action.
            body (Dict[str, JsonValue]): Its JSON body.
            meta (Dict[str, JsonValue]): The request meta.

        Returns:
            Request: The POST request.
        """
        self.price_pending += 1
        return self._price_request(self._api_url(action), {**meta, self.ACTION_META: action.value}, body)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price navigation, listing the products and their price templates, and the documentation home.

        Yields:
            Request: The navigation call and the documentation home.
        """
        self.price_pending = 0
        self.price_rows = 0
        self.price_templates = {}
        self.logger.info("Reading the Volcano Engine prices from %s.", self.NAVIGATION_URL)
        yield self._api_request(VolcanoEnginePriceAction.NAVIGATION, {}, {})
        yield self._price_request(self.DOCS_HOME_URL, {self.DOCS_STAGE_META: VolcanoEngineDocStage.HOME.value})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a call of the price API (the navigation, a template or a price table) or a documentation request.

        Args:
            response (Response): The answer of the call.

        Yields:
            PriceFact: The calls it leads to (each template of the navigation, the prices of a template), or the
                prices of a table.

        Raises:
            CatalogueFormatError: If the call has no result.
        """
        if self.DOCS_STAGE_META in response.meta:
            for fact in self._docs_facts(response):
                yield fact
            return
        meta: Dict[str, JsonValue] = dict(response.meta)
        action = meta.get(self.ACTION_META)
        try:
            result = self._api_result(response)
        except CatalogueFormatError:
            self.price_failures.add(response.url)
            self._price_settled()
            raise
        code = str(meta.get(self.TEMPLATE_META) or "")
        if action == VolcanoEnginePriceAction.NAVIGATION:
            navigation = result.get(VolcanoEnginePriceField.NAVIGATION)
            nodes: JsonValue = json.loads(navigation) if isinstance(navigation, str) else navigation
            for product, category in self._leaf_products(nodes, ""):
                infos = product.get(VolcanoEnginePriceField.TEMPLATE_INFO_LIST)
                for info in infos if isinstance(infos, list) else []:
                    template = info.get(VolcanoEnginePriceField.TEMPLATE_CODE) if isinstance(info, dict) else None
                    if not isinstance(info, dict) or info.get(VolcanoEnginePriceField.TYPE) != self.DETAILS_TEMPLATE:
                        continue
                    if isinstance(template, str) and template:
                        yield self._api_request(
                            VolcanoEnginePriceAction.TEMPLATE,
                            {VolcanoEnginePriceField.TEMPLATE_CODE.value: template},
                            {
                                self.TEMPLATE_META: template,
                                self.PRODUCT_NAME_META: product.get(VolcanoEnginePriceField.PRODUCT_ZH_NAME)
                                or product.get(VolcanoEnginePriceField.PRODUCT),
                                self.CATEGORY_META: category,
                            },
                        )
        elif action == VolcanoEnginePriceAction.TEMPLATE:
            items: Dict[str, Dict[str, JsonValue]] = {}
            listed = result.get(VolcanoEnginePriceField.LIST)
            for entry in listed if isinstance(listed, list) else []:
                definition = entry.get(VolcanoEnginePriceField.TEMPLATE) if isinstance(entry, dict) else None
                self._charge_items(json.loads(definition) if isinstance(definition, str) else definition, items)
            self.price_templates[code] = items
            yield self._api_request(
                VolcanoEnginePriceAction.TABLE, {VolcanoEnginePriceField.TEMPLATE_CODE.value: code}, meta
            )
        else:
            items = self.price_templates.pop(code, {})
            tables = result.get(VolcanoEnginePriceField.TABLE_LIST)
            found = 0
            for table in tables if isinstance(tables, list) else []:
                rows = table.get(VolcanoEnginePriceField.ROWS) if isinstance(table, dict) else None
                for row in rows if isinstance(rows, list) else []:
                    for fact in self._row_prices(row, items, meta) if isinstance(row, dict) else iter(()):
                        found += 1
                        yield fact
            self.price_rows += found
            self.logger.debug("Volcano Engine template %s: %d prices.", code, found)
        self._price_settled()

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page, duplicates included.
        """
        self.logger.debug("Reading the %s catalogue of %s.", self.name, response.url)
        return self._catalogue_products(response)
