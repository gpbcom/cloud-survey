from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, Optional
from urllib.parse import urljoin

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.enums import HtmlAttribute
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class SelectelMarketplaceCrawler(BaseMarketplaceCrawler):
    """Selectel marketplace crawler: the ready-made images of the AI marketplace (`ИИ-маркетплейс`).

    Attributes:
        ROWS (ClassVar[str]): The selector of the rows of the images table.
        NAME (ClassVar[str]): The selector of the image link of a row, holding its name and documentation page.
        DESCRIPTION (ClassVar[str]): The selector of the image description cell of a row.

    Notes:
        The AI marketplace creates cloud servers from images with preconfigured machine learning, data analysis and
        AI agent tools (e.g. `n8n Virtual Machine`, `Dify Virtual Machine`). The marketing page
        https://selectel.ru/solutions/ai-infrastructure/ai-marketplace/ shows a selection of them, without links. The
        documentation page https://docs.selectel.ru/ai-marketplace/about/about-ai-marketplace/ (rendered on the
        server, read over HTTP) lists every image in its `Готовые образы` table: a row per image, with its name
        linked to its documentation page and its description. The images are cloud servers (`virtual-machine`
        delivery). The page gives no publisher, no category and no date: the software has no marketplace category.
        The Russian names and descriptions are kept as written.
    """

    ROWS: ClassVar[str] = "table tr"
    NAME: ClassVar[str] = "th a"
    DESCRIPTION: ClassVar[str] = "td"

    name = "selectel-marketplace"
    catalogue_url: ClassVar[str] = "https://docs.selectel.ru/ai-marketplace/about/about-ai-marketplace/"

    ############################
    # Internal Helpers Methods #
    ############################

    def _row_software(self, row: Selector, page_url: str) -> Optional[MarketplaceSoftware]:
        """Build the software of a row of the images table.

        Args:
            row (Selector): The table row.
            page_url (str): The URL of the page, against which the relative links are resolved.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` (logged) for a row without image link or an invalid
                entry.
        """
        link = row.css(self.NAME).first
        if link is None:
            self.logger.debug("Skipping a %s table row without image link.", self.name)
            return None
        cell = row.css(self.DESCRIPTION).first
        href = link.attrib.get(HtmlAttribute.HREF)
        return self._build_software(
            link.get_all_text(separator=" ", strip=True),
            cell.get_all_text(separator=" ", strip=True) if cell is not None else None,
            urljoin(page_url, href) if href else None,
            delivery=DeliveryMethod.VIRTUAL_MACHINE,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the images of the table of the documentation page.

        Args:
            response (Response): The AI marketplace documentation page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid image of the table.
        """
        rows = response.css(self.ROWS)
        self.logger.debug("%d table rows in the %s page %s.", len(rows), self.name, response.url)
        for row in rows:
            if (software := self._row_software(row, response.url)) is not None:
                yield software
