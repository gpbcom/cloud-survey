from __future__ import annotations

# Standard Library Imports.
import contextlib
import os
from pathlib import Path


class AtomicJsonFile:
    """A JSON file written atomically: readers never see a partially written file.

    Attributes:
        path (Path): The file path.
    """

    def __init__(self, path: Path) -> None:
        """Initialize the file.

        Args:
            path (Path): The file path.
        """
        self.path = path

    ############################
    # Publicly Exposed Methods #
    ############################

    def write(self, content: str) -> None:
        """Write the file through a temporary file renamed over it, creating its folder when missing.

        Args:
            content (str): The JSON document.

        Raises:
            OSError: If the folder or the file cannot be written (the temporary file is removed).
        """
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(content + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise
