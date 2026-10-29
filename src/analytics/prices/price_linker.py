from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse


class PriceLinker:
    """Match the services of the current prices of a provider to its live catalogue products.

    Attributes:
        PARENTHESES (ClassVar[re.Pattern[str]]): A parenthesized note of a name, e.g. `(ECS)`, ignored.
        NOT_WORD (ClassVar[re.Pattern[str]]): The characters a comparison key leaves out.
        MIN_CONTAINED (ClassVar[int]): The shortest key matched by containment (a shorter one matches too much).
        logger (Logger): The linker logger.

    Notes:
        A priced service (its name and the page or API it was read from) is linked to a product by the first rule
        that gives a single product:
        1. Its name and the product name have the same key (case, brand prefix, parenthesized notes and
           punctuation ignored).
        2. It was read from the product page (not a section of a shared page, e.g. `pricing#object-store`).
        3. One key contains the other, both of `MIN_CONTAINED` characters at least.
        The collector applies the curated row links first. Then a curated statement (named as its product) is
        linked to its product, then the curated links of the provider (`CoverageCatalog.links`) are tried before
        any automatic rule (a crawled service named as a broad product, e.g. Azure `Storage`, is split by them). A
        service whose prices name their product (the product detail, e.g. Azure `productName`) is matched by that
        detail, then by its name.
        A service matching several products is left unlinked rather than guessed.
    """

    PARENTHESES: ClassVar[re.Pattern[str]] = re.compile(r"[(\uff08][^)\uff09]*[)\uff09]")
    NOT_WORD: ClassVar[re.Pattern[str]] = re.compile(r"[\W_]+")
    MIN_CONTAINED: ClassVar[int] = 5

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the linker.

        Args:
            logger (Optional[Logger]): The linker logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Price linker ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _key(self, name: str, prefixes: Sequence[str]) -> str:
        """Normalize a name to compare it.

        Args:
            name (str): A product or service name.
            prefixes (Sequence[str]): The brand prefixes of the provider, e.g. `Amazon `.

        Returns:
            str: The comparison key, e.g. `ec2` for `Amazon EC2`.
        """
        text = self.PARENTHESES.sub(" ", name.casefold()).strip()
        for prefix in sorted(prefixes, key=len, reverse=True):
            if text.startswith(prefix.casefold()):
                text = text[len(prefix) :]
                break
        return self.NOT_WORD.sub("", text)

    def _url_key(self, url: Optional[str]) -> str:
        """Normalize a page URL to compare it: scheme, `www.`, query, fragment and trailing slash are ignored.

        Args:
            url (Optional[str]): The URL.

        Returns:
            str: The comparison key, empty without URL.
        """
        if not url:
            return ""
        link = urlparse(url.casefold())
        return f"{link.netloc.removeprefix('www.')}{link.path.rstrip('/')}"

    def _contained(self, key: str, keys: Dict[str, Set[int]]) -> Set[int]:
        """Find the products whose key contains a service key, or is contained in it.

        Args:
            key (str): The service key.
            keys (Dict[str, Set[int]]): The products of each product key.

        Returns:
            Set[int]: The matching products.
        """
        if len(key) < self.MIN_CONTAINED:
            return set()
        return {
            product
            for other, products in keys.items()
            if len(other) >= self.MIN_CONTAINED and (other in key or key in other)
            for product in products
        }

    def _curated(
        self, products: Dict[int, Tuple[str, Optional[str]]], curated: Mapping[str, Sequence[str]]
    ) -> List[Tuple[int, List[re.Pattern[str]]]]:
        """Compile the curated links of the live products.

        Args:
            products (Dict[int, Tuple[str, Optional[str]]]): The name and page of each live product, by identifier.
            curated (Mapping[str, Sequence[str]]): The regular expressions of the priced services of each product,
                by product name.

        Returns:
            List[Tuple[int, List[re.Pattern[str]]]]: Each live product with curated links and its expressions, in
                the curated order.
        """
        by_name = {name.casefold(): product for product, (name, _) in products.items()}
        compiled: List[Tuple[int, List[re.Pattern[str]]]] = []
        for name, patterns in curated.items():
            product = by_name.get(name.casefold())
            if product is None:
                self.logger.warning(
                    "The curated product %r is not a live catalogue product: its links are unused.", name
                )
                continue
            compiled.append((product, [re.compile(pattern, re.IGNORECASE) for pattern in patterns]))
        return compiled

    ############################
    # Publicly Exposed Methods #
    ############################

    def exact_links(
        self,
        products: Dict[int, Tuple[str, Optional[str]]],
        services: Sequence[Tuple[str, str, str]],
        marker: str,
    ) -> List[Tuple[str, str, str, int]]:
        """Match the marked priced services (the curated statements) named exactly as a live product (case ignored).

        Args:
            products (Dict[int, Tuple[str, Optional[str]]]): The name and page of each live product, by identifier.
            services (Sequence[Tuple[str, str, str]]): The priced services: their name, source and product detail.
            marker (str): The text the source of a matched service holds, e.g. the statement fragment.

        Returns:
            List[Tuple[str, str, str, int]]: The service, source, product detail and product of each exact match.

        Notes:
            Only the marked services are matched here: a crawled service named as a broad product (e.g. Azure
            `Storage`) is left to the curated links, which split it by product detail.
        """
        names = {name.casefold(): product for product, (name, _) in products.items()}
        links = [
            (service, source, detail, names[service.casefold()])
            for service, source, detail in services
            if marker in source and service.casefold() in names
        ]
        self.logger.debug("%d marked priced services named exactly as a product.", len(links))
        return links

    def row_links(
        self, products: Dict[int, Tuple[str, Optional[str]]], curated: Mapping[str, Sequence[str]]
    ) -> List[Tuple[str, int]]:
        """Resolve the curated row links to live products.

        Args:
            products (Dict[int, Tuple[str, Optional[str]]]): The name and page of each live product, by identifier.
            curated (Mapping[str, Sequence[str]]): The regular expressions of the price rows of each product,
                by product name.

        Returns:
            List[Tuple[str, int]]: Each expression and its product, in the curated order.
        """
        by_name = {name.casefold(): product for product, (name, _) in products.items()}
        links: List[Tuple[str, int]] = []
        for name, patterns in curated.items():
            product = by_name.get(name.casefold())
            if product is None:
                self.logger.warning(
                    "The curated product %r is not a live catalogue product: its row links are unused.", name
                )
                continue
            links.extend((pattern, product) for pattern in patterns)
        self.logger.debug("%d curated row links resolved.", len(links))
        return links

    def links(
        self,
        products: Dict[int, Tuple[str, Optional[str]]],
        services: Sequence[Tuple[str, str, str]],
        prefixes: Sequence[str] = (),
        curated: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> List[Tuple[str, str, str, int]]:
        """Match priced services to catalogue products.

        Args:
            products (Dict[int, Tuple[str, Optional[str]]]): The name and page of each live product, by identifier.
            services (Sequence[Tuple[str, str, str]]): The priced services: their name, source and product detail.
            prefixes (Sequence[str]): The brand prefixes of the provider.
            curated (Optional[Mapping[str, Sequence[str]]]): The curated links: the regular expressions matching
                the priced services (their name or product detail) of each product, by product name.

        Returns:
            List[Tuple[str, str, str, int]]: The service, source, product detail and product of each link found.
        """
        if not products:
            self.logger.warning("No live catalogue product to link %d priced services to.", len(services))
            return []
        rules = self._curated(products, curated or {})
        keys: Dict[str, Set[int]] = {}
        pages: Dict[str, int] = {}
        for product, (name, url) in products.items():
            keys.setdefault(self._key(name, prefixes), set()).add(product)
            if (url_key := self._url_key(url)) and not urlparse(url or "").fragment:
                pages[url_key] = product
        names = {name.casefold(): product for product, (name, _) in products.items()}
        links: List[Tuple[str, str, str, int]] = []
        for service, source, detail in services:
            chosen = next(
                (
                    product
                    for product, patterns in rules
                    if any(pattern.search(service) or (detail and pattern.search(detail)) for pattern in patterns)
                ),
                None,
            )
            if chosen is None:
                chosen = names.get(service.casefold())
            key = self._key(detail or service, prefixes)
            exact = keys.get(key, set()) if key else set()
            page = pages.get(self._url_key(source))
            contained: Set[int] = self._contained(key, keys) if len(exact) != 1 and page is None else set()
            if chosen is None and len(exact) == 1:
                chosen = next(iter(exact))
            elif chosen is None and page is not None:
                chosen = page
            elif chosen is None and len(contained) == 1:
                chosen = next(iter(contained))
            if chosen is None and detail:
                fallback = keys.get(self._key(service, prefixes), set())
                chosen = next(iter(fallback)) if len(fallback) == 1 else None
            if chosen is None:
                self.logger.debug("The priced service %r (%s) matches no single product: not linked.", service, detail)
                continue
            links.append((service, source, detail, chosen))
        self.logger.info("%d of %d priced services linked to a catalogue product.", len(links), len(services))
        return links
