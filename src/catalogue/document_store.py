from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional, Type

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from catalogue.atomic_json_file import AtomicJsonFile
from catalogue.exception import CatalogueFileError, CatalogueWriteError
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider
from models.cloud.marketplace import CloudMarketplace


class DocumentStore[DocumentT: (CloudCatalogue, CloudMarketplace)]:
    """Store of crawled documents (catalogues or marketplaces): one `<provider>.json` file per cloud provider.

    Attributes:
        output_dir (Path): The folder holding the files, created on the first save.
        document_type (Type[DocumentT]): The stored document model.
        kind (str): The document kind, in the logs and errors, e.g. `catalogue`.
        unit (str): The document items, in the logs, e.g. `products`.
        logger (Logger): The store logger.
    """

    def __init__(
        self,
        output_dir: Path,
        document_type: Type[DocumentT],
        kind: str,
        unit: str,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the store.

        Args:
            output_dir (Path): The folder holding the files, created on the first save.
            document_type (Type[DocumentT]): The stored document model.
            kind (str): The document kind, in the logs and errors, e.g. `catalogue`.
            unit (str): The document items, in the logs, e.g. `products`.
            logger (Optional[Logger]): The store logger.
        """
        self.output_dir = output_dir
        self.document_type: Type[DocumentT] = document_type
        self.kind = kind
        self.unit = unit
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def path_for(self, provider: CloudProvider) -> Path:
        """Get the file path of a cloud provider.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Path: The file path, e.g. `output/scaleway.json`.
        """
        return self.output_dir / f"{provider.value}.json"

    def save(self, document: DocumentT) -> Path:
        """Write a document file, atomically: readers never see a partially written file.

        Args:
            document (DocumentT): The document to write.

        Returns:
            Path: The written file path.

        Raises:
            CatalogueWriteError: If the folder or the file cannot be written.
        """
        path = self.path_for(document.provider)
        self.logger.debug("Writing the %s %s to %s.", document.provider.value, self.kind, path)
        try:
            AtomicJsonFile(path).write(document.model_dump_json(indent=2))
        except OSError as e:
            self.logger.error("The %s %s cannot be written to %s: %s", document.provider.value, self.kind, path, e)
            raise CatalogueWriteError(path, e.strerror or str(e)) from e
        self.logger.info("%d %s %s written to %s.", document.size, document.provider.value, self.unit, path)
        return path

    def load(self, provider: CloudProvider) -> Optional[DocumentT]:
        """Read the document file of a cloud provider.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Optional[DocumentT]: The document, `None` when the provider was never crawled (no file).

        Raises:
            CatalogueFileError: If the file cannot be read or does not hold a valid document of the provider.
        """
        path = self.path_for(provider)
        if not path.exists():
            self.logger.debug("No %s %s at %s: never crawled.", provider.value, self.kind, path)
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            self.logger.error("The %s %s %s cannot be read: %s", provider.value, self.kind, path, e)
            raise CatalogueFileError(path, f"the file cannot be read ({e.strerror})") from e
        try:
            document = self.document_type.model_validate_json(raw)
        except ValidationError as e:
            is_json = all(error["type"] != "json_invalid" for error in e.errors())
            reason = f"invalid {self.kind} ({e.error_count()} errors)" if is_json else "the file is not valid JSON"
            self.logger.error("The %s %s %s is unusable: %s.", provider.value, self.kind, path, reason)
            raise CatalogueFileError(path, reason) from e
        if document.provider is not provider:
            self.logger.error("The file %s holds the %s %s.", path, document.provider.value, self.kind)
            raise CatalogueFileError(path, f"it holds the {document.provider.value} {self.kind}")
        self.logger.info("%d %s %s loaded from %s.", document.size, provider.value, self.unit, path)
        return document
