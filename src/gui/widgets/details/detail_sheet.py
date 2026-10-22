from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote

# First Party Imports.
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.categorized_item import CategorizedItem
from models.storage.enums import ItemFilter
from models.taxonomy.enums import CategorySource

Chip = Tuple[str, Optional[ItemFilter], str, Optional[str]]


class DetailSheet:
    """Writer of the rich text of the details panels: captioned fields, chips filtering the table, links.

    Attributes:
        SCHEME (ClassVar[str]): The scheme of the links asking the view to filter on a value.
        SOURCE_NOTES (ClassVar[Dict[CategorySource, str]]): The note shown next to categories not given by the rules.
        theme (Theme): The application theme.
        logger (Logger): The sheet logger.

    Notes:
        - A chip is a text, the filter it sets when clicked (`None` for a plain chip), the value it filters on and
          its background colour (`None` for the panel colour).
        - A filter link is `filter:<ItemFilter>:<quoted value>`, read back by `read_href`.
    """

    SCHEME: ClassVar[str] = "filter"
    SOURCE_NOTES: ClassVar[Dict[CategorySource, str]] = {
        CategorySource.USER: "set by hand",
        CategorySource.LLM: "suggested by the language model",
    }

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize the writer.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The sheet logger.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def href(self, item_filter: ItemFilter, value: str) -> str:
        """Write the link filtering the table on a value.

        Args:
            item_filter (ItemFilter): The filter.
            value (str): The value filtered on.

        Returns:
            str: The link, e.g. `filter:catalogue-categories:Compute`.
        """
        return f"{self.SCHEME}:{item_filter.value}:{quote(value, safe='')}"

    def read_href(self, href: str) -> Optional[Tuple[ItemFilter, str]]:
        """Read a filter link.

        Args:
            href (str): The clicked link.

        Returns:
            Optional[Tuple[ItemFilter, str]]: The filter and its value, `None` for another link (a web page).
        """
        scheme, _, rest = href.partition(":")
        name, _, value = rest.partition(":")
        if scheme != self.SCHEME or name not in {item_filter.value for item_filter in ItemFilter}:
            self.logger.debug("Link %r is not a filter link.", href)
            return None
        return ItemFilter(name), unquote(value)

    def chips(self, chips: List[Chip]) -> str:
        """Write a row of chips.

        Args:
            chips (List[Chip]): The text, filter, value and colour of each chip.

        Returns:
            str: The rich text chips, empty without chip.
        """
        written: List[str] = []
        for text, item_filter, value, color in chips:
            background = color or self.theme.SURFACE_ALT
            foreground = "#11151c" if color else self.theme.TEXT
            label = html.escape(text)
            if item_filter is not None:
                link = html.escape(self.href(item_filter, value), quote=True)
                label = f'<a href="{link}" style="color:{foreground}; text-decoration:none;">{label}</a>'
            written.append(
                f'<span style="background-color:{background}; color:{foreground}; font-weight:600;">'
                f"&nbsp;{label}&nbsp;</span>"
            )
        return " ".join(written)

    def field(self, caption: str, value: str) -> str:
        """Write a captioned field.

        Args:
            caption (str): What the field is, e.g. `Catalogue categories`.
            value (str): Its rich text value.

        Returns:
            str: The caption above the value, empty when the value is empty.
        """
        if not value:
            return ""
        return (
            f'<p style="margin:0 0 10px 0;"><span style="color:{self.theme.TEXT_MUTED}; font-size:11px;">'
            f"{html.escape(caption.upper())}</span><br>{value}</p>"
        )

    def link(self, url: Optional[str], text: str) -> str:
        """Write a link to a web page.

        Args:
            url (Optional[str]): The page address.
            text (str): The link text.

        Returns:
            str: The rich text link, empty without address.
        """
        if not url:
            return ""
        return f'<a href="{html.escape(url, quote=True)}" style="color:{self.theme.ACCENT};">{html.escape(text)}</a>'

    def lines(self, text: str) -> str:
        """Write a plain text, its line breaks kept.

        Args:
            text (str): The text.

        Returns:
            str: The escaped text, its lines separated by `<br>`.
        """
        return "<br>".join(html.escape(line) for line in text.splitlines())

    def categorization(self, item: CategorizedItem, cache: TaxonomyCache) -> str:
        """Write the unified categories of an item and its source labels.

        Args:
            item (CategorizedItem): The item.
            cache (TaxonomyCache): The names of the categories and of the labels.

        Returns:
            str: The "Categories" field (`Domain > Category` chips, the domains of an item filed in a domain only, and
                a note when a person or the language model set them), then the "Source labels" field (English names,
                the original text in parentheses, the raw labels while the stored ones are not read).
        """
        chips: List[Chip] = [
            (cache.path(slug), ItemFilter.SERVICE_CATEGORIES, slug, None) for slug in item.service_categories
        ]
        if not chips:
            chips = [(cache.name(slug), ItemFilter.SERVICE_CATEGORIES, slug, None) for slug in item.service_domains]
        if chips:
            categories = self.chips(chips)
            note = self.SOURCE_NOTES.get(item.categories_source) if item.categories_source else None
            if note:
                categories += f' <span style="color:{self.theme.TEXT_MUTED};">({html.escape(note)})</span>'
        else:
            categories = f'<span style="color:{self.theme.TEXT_MUTED};">Not categorized yet</span>'
        labels: List[Chip] = []
        for label_id in item.source_label_ids:
            label = cache.labels.get(label_id)
            if label is None:
                continue
            name = label.display_name()
            text = name if label.text == name else f"{name} ({label.text})"
            labels.append((text, ItemFilter.SOURCE_LABELS, str(label_id), None))
        if not labels:
            labels = [(raw, None, raw, None) for raw in item.raw_labels()]
        self.logger.debug("Categorization written: %d categories, %d labels.", len(chips), len(labels))
        return self.field("Categories", categories) + self.field("Source labels", self.chips(labels))
