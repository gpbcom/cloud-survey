from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Final, Optional

# First Party Imports.
from catalogue.document_store import DocumentStore
from models.cloud.marketplace import CloudMarketplace

DEFAULT_MARKETPLACE_DIR: Final[Path] = Path("output") / "marketplaces"


class MarketplaceStore(DocumentStore[CloudMarketplace]):
    """Store of the crawled marketplaces: one `<provider>.json` file per cloud provider."""

    def __init__(self, output_dir: Path = DEFAULT_MARKETPLACE_DIR, logger: Optional[Logger] = None) -> None:
        """Initialize the store.

        Args:
            output_dir (Path): The folder holding the marketplace files, created on the first save.
            logger (Optional[Logger]): The store logger.
        """
        store_logger = logger if logger else getLogger(__name__)
        super().__init__(output_dir, CloudMarketplace, "marketplace", "software", store_logger)
