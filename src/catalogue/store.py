from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Final, Optional

# First Party Imports.
from catalogue.document_store import DocumentStore
from models.cloud.catalogue import CloudCatalogue

DEFAULT_OUTPUT_DIR: Final[Path] = Path("output")


class CatalogueStore(DocumentStore[CloudCatalogue]):
    """Store of the crawled catalogues: one `<provider>.json` file per cloud provider."""

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR, logger: Optional[Logger] = None) -> None:
        """Initialize the store.

        Args:
            output_dir (Path): The folder holding the catalogue files, created on the first save.
            logger (Optional[Logger]): The store logger.
        """
        super().__init__(output_dir, CloudCatalogue, "catalogue", "products", logger if logger else getLogger(__name__))
