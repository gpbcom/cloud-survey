from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal

# First Party Imports.
from gui.storage_bridge.storage_loop import StorageLoop
from models.taxonomy.labels.source_label import SourceLabel
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.exception import StorageError
from taxonomy.seed_loader import TaxonomySeedLoader


class TaxonomyCache(QObject):
    """The unified taxonomy and the names of the source labels, as the GUI shows them, read from the storage.

    Attributes:
        PATH_SEPARATOR (ClassVar[str]): The separator of a domain and its category in a readable path.
        LANGUAGE_NAMES (ClassVar[Dict[str, str]]): The name of each language of the labels.
        changed (pyqtSignal): Emitted when the taxonomy or the labels were read again.
        loop (Optional[StorageLoop]): The storage thread of the GUI, `None` to keep the seed of the project.
        taxonomy (Taxonomy): The taxonomy: the seed of the project until the stored one is read.
        labels (Dict[int, SourceLabel]): The stored source labels, by identifier.
        logger (Logger): The cache logger.

    Notes:
        The cache is read when the views refresh their figures (a crawl or an edit may have changed it). The seed of
        the project names the categories before the storage answers (or without storage).
    """

    PATH_SEPARATOR: ClassVar[str] = " > "
    LANGUAGE_NAMES: ClassVar[Dict[str, str]] = {"en": "English", "ru": "Russian", "zh": "Chinese"}

    changed = pyqtSignal()

    def __init__(self, loop: Optional[StorageLoop] = None, logger: Optional[Logger] = None) -> None:
        """Build the cache with the seed of the project.

        Args:
            loop (Optional[StorageLoop]): The storage thread of the GUI.
            logger (Optional[Logger]): The cache logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.loop = loop
        self.taxonomy = TaxonomySeedLoader(self.logger).load_taxonomy()
        self.labels: Dict[int, SourceLabel] = {}
        self.logger.debug("Taxonomy cache built from the seed: %d nodes.", len(self.taxonomy.nodes))

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_taxonomy(self, taxonomy: Taxonomy) -> None:
        """Keep the stored taxonomy.

        Args:
            taxonomy (Taxonomy): The stored taxonomy.
        """
        self.logger.debug("Stored taxonomy cached: %d nodes.", len(taxonomy.nodes))
        if taxonomy.nodes:
            self.taxonomy = taxonomy
        self.changed.emit()

    def _on_labels(self, labels: List[SourceLabel]) -> None:
        """Keep the stored labels.

        Args:
            labels (List[SourceLabel]): The stored labels.
        """
        self.logger.debug("%d source labels cached.", len(labels))
        self.labels = {label.id: label for label in labels}
        self.changed.emit()

    def _on_error(self, error: StorageError) -> None:
        """Keep the cache as it is when the storage cannot be read.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The taxonomy cannot be read, its last version is kept: %s", error)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Read the stored taxonomy and labels again, telling when they are read."""
        if self.loop is None:
            self.logger.debug("No storage: the taxonomy cache keeps the seed.")
            return
        self.logger.debug("Reading the stored taxonomy and labels.")
        self.loop.submit(lambda storage: storage.taxonomy.list(), self._on_taxonomy, self._on_error)
        self.loop.submit(lambda storage: storage.labels.read_all(), self._on_labels, self._on_error)

    def name(self, slug: str) -> str:
        """Get the English name of a taxonomy node.

        Args:
            slug (str): The node slug.

        Returns:
            str: Its English name, the slug when the node is unknown.
        """
        node = self.taxonomy.node(slug)
        return node.name_en if node is not None else slug

    def path(self, slug: str) -> str:
        """Get the readable path of a node: its domain, then the category.

        Args:
            slug (str): The node slug.

        Returns:
            str: e.g. `Databases > Relational databases`, the name alone for a domain.
        """
        domain = self.taxonomy.domain_of(slug)
        if domain is None or domain == slug:
            return self.name(slug)
        return f"{self.name(domain)}{self.PATH_SEPARATOR}{self.name(slug)}"

    def description(self, slug: str) -> str:
        """Get the description of a taxonomy node.

        Args:
            slug (str): The node slug.

        Returns:
            str: Its one-line description, empty when unknown.
        """
        node = self.taxonomy.node(slug)
        return node.description_en if node is not None else ""

    def names(self, slugs: Sequence[str]) -> str:
        """Get the English names of some nodes, for a table cell.

        Args:
            slugs (Sequence[str]): The node slugs.

        Returns:
            str: Their names, comma separated.
        """
        return ", ".join(self.name(slug) for slug in slugs)

    def label_name(self, label_id: int) -> Optional[str]:
        """Get the name shown for a source label.

        Args:
            label_id (int): The label identifier.

        Returns:
            Optional[str]: Its English name (its text while it is not translated), `None` when it is not read yet.
        """
        label = self.labels.get(label_id)
        return label.display_name() if label is not None else None

    def label_tooltip(self, label_id: int) -> str:
        """Get the tooltip of a source label: its original text and language.

        Args:
            label_id (int): The label identifier.

        Returns:
            str: e.g. `Базы данных (Russian)`, empty when it is not read yet.
        """
        label = self.labels.get(label_id)
        if label is None:
            return ""
        status = "" if label.name_en else ", not translated yet"
        return f"{label.text} ({self.LANGUAGE_NAMES.get(label.language.value, label.language.value)}{status})"

    def label_names(self, label_ids: Sequence[int], fallback: Sequence[str] = ()) -> str:
        """Get the names of the source labels of an item, for a table cell.

        Args:
            label_ids (Sequence[int]): The label identifiers.
            fallback (Sequence[str]): The raw labels, shown when the identifiers are not read yet.

        Returns:
            str: The names, comma separated, each once.
        """
        names = [name for label_id in label_ids if (name := self.label_name(label_id)) is not None]
        return ", ".join(dict.fromkeys(names or list(fallback)))
