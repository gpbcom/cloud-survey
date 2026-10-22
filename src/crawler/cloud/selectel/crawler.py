from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.selectel.enums import SelectelMenu, SelectelMenuGroup
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class SelectelCrawler(BaseCloudCrawler):
    """Selectel catalogue crawler.

    Attributes:
        MENU (ClassVar[str]): The top entries of the header menu, each one with its title and its dropdown.
        MENU_TITLE (ClassVar[str]): The title button of a top entry of the header menu, e.g. `Продукты`.
        GROUP (ClassVar[str]): The groups of a dropdown, each one with its title and its links.
        GROUP_TITLE (ClassVar[str]): The title of a dropdown group, e.g. `Базы данных`.
        LINK (ClassVar[str]): The product links of a dropdown group.
        LINK_ANCHOR (ClassVar[str]): The anchor of a product link, holding the product page.
        NAME (ClassVar[str]): The product name of a product link, without its status badge (`New`, `Free`).
        DESCRIPTION (ClassVar[str]): The product description of a product link.
        MENUS (ClassVar[Tuple[SelectelMenu, ...]]): The titles of the top entries of the header menu listing offers.
        SKIPPED_GROUPS (ClassVar[Tuple[SelectelMenuGroup, ...]]): The titles of the dropdown groups which are not
            catalogue categories.

    Notes:
        The https://selectel.ru/services/ page (rendered on the server by Nuxt, read over HTTP) carries the full
        header menu of the website. Its `Продукты` (products) and `Услуги` (services) entries open a dropdown of
        groups, each group listing links with a product name, a description and the product page. A product is
        filed under the title of the top entry, then the title of its group (e.g. `Продукты`, `Базы данных`), and
        under those of every group listing it. The `Популярные` group is a selection of products listed in the other
        groups, the `Бизнес-задачи` group lists use-case pages and the `Отрасли` group lists industries: they are not
        read. The English website has no product menu, the Russian names are kept as written. The page sitemap
        dates some product pages (`lastmod`).
    """

    MENU: ClassVar[str] = "li.main-nav__list-item"
    MENU_TITLE: ClassVar[str] = "button.main-nav__list-btn"
    GROUP: ClassVar[str] = ".nav-dropdown__body-inner"
    GROUP_TITLE: ClassVar[str] = ".nav-dropdown__return-btn--subcategory"
    LINK: ClassVar[str] = ".menu-link"
    LINK_ANCHOR: ClassVar[str] = "a.menu-link__title"
    NAME: ClassVar[str] = ".menu-link__title-text"
    DESCRIPTION: ClassVar[str] = ".menu-link__description"
    MENUS: ClassVar[Tuple[SelectelMenu, ...]] = (SelectelMenu.PRODUCTS, SelectelMenu.SERVICES)
    SKIPPED_GROUPS: ClassVar[Tuple[SelectelMenuGroup, ...]] = (
        SelectelMenuGroup.POPULAR,
        SelectelMenuGroup.BUSINESS_TASKS,
        SelectelMenuGroup.INDUSTRIES,
    )

    name = "selectel"
    catalogue_url: ClassVar[str] = "https://selectel.ru/services/"
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ("https://selectel.ru/sitemap-pages.xml",)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Selectel ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Normalize a product URL to compare it, keeping its query.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The comparison key, e.g. `selectel.ru/services/additional/firewall?section=virtualfirewall`.

        Notes:
            The menu links distinct products to sections of one page (`?section=`, `?tab=`), e.g. the hardware and
            the virtual firewalls: the query tells them apart.
        """
        query = urlparse(url.casefold()).query
        key = super()._url_key(url)
        return f"{key}?{query}" if query else key

    def _text(self, element: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element matching a selector.

        Args:
            element (Selector): The element searched.
            selector (str): The CSS selector of the element read.

        Returns:
            Optional[str]: The element text, whitespaces collapsed, `None` when there is no such element.
        """
        found = element.css(selector).first
        return self._clean_text(found.get_all_text(separator=" ", strip=True)) if found is not None else None

    def _link_product(self, link: Selector, page_url: str, categories: List[str]) -> Optional[CloudProduct]:
        """Build the product of a menu link.

        Args:
            link (Selector): The menu link.
            page_url (str): The URL of the page, against which the relative links are resolved.
            categories (List[str]): The titles of the menu entry and of the group listing the link.

        Returns:
            Optional[CloudProduct]: The product, `None` (logged) when the link is invalid.
        """
        anchor = link.css(self.LINK_ANCHOR).first
        href = anchor.attrib.get(HtmlAttribute.HREF) if anchor is not None else None
        return self._build_product(
            self._text(link, self.NAME),
            self._text(link, self.DESCRIPTION),
            urljoin(page_url, href) if href else None,
            categories=categories,
        )

    def _group_products(self, menu: Selector, menu_title: str, page_url: str) -> Iterator[CloudProduct]:
        """Build the products of the groups of a menu entry, filed under the entry and group titles.

        Args:
            menu (Selector): The top entry of the header menu.
            menu_title (str): Its title, e.g. `Продукты`.
            page_url (str): The URL of the page, against which the relative links are resolved.

        Yields:
            Iterator[CloudProduct]: The valid product of each link of the read groups, an occurrence per group.
        """
        for group in menu.css(self.GROUP):
            title = self._text(group, self.GROUP_TITLE)
            if title in self.SKIPPED_GROUPS:
                self.logger.debug("Skipping the menu group %r of %r, not a catalogue category.", title, menu_title)
                continue
            links = group.css(self.LINK)
            self.logger.debug("%d links in the menu group %r of %r.", len(links), title, menu_title)
            for link in links:
                if product := self._link_product(link, page_url, [menu_title, title or ""]):
                    yield product

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Build the products of the read entries of the header menu, an occurrence per group listing them.

        Args:
            response (Response): The services page.

        Yields:
            Iterator[CloudProduct]: Each valid product occurrence, by order of appearance.
        """
        for menu in response.css(self.MENU):
            title = self._text(menu, self.MENU_TITLE)
            if title not in self.MENUS:
                self.logger.debug("Skipping the menu entry %r, it lists no offer.", title)
                continue
            yield from self._group_products(menu, title, response.url)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the header menu, each one once with the categories of all its groups.

        Args:
            response (Response): The services page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.
        """
        products = self._merge_categories(self._menu_products(response))
        self.logger.debug("%d products in the %s header menu of %s.", len(products), self.name, response.url)
        return iter(products)
