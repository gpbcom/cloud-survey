from __future__ import annotations

# Standard Library Imports.
import hashlib
import json
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from pydantic import JsonValue, ValidationError

# First Party Imports.
from conf import CURATED_DIR
from curated.exception import CuratedBundleError
from models.curated.enums import CuratedDataset, CuratedFile, IdentifierKind
from models.curated.records.curated_bundle import CuratedBundle


class BundleFiles:
    """Read and write the curated bundle: a JSON file per catalogue in `data/curated/`.

    Attributes:
        FIELDS (ClassVar[Dict[CuratedFile, List[Tuple[str, str]]]]): The lists of each file: the key in the file and
            the field of the bundle (the records of a file are those of its sections).
        PREFIXES (ClassVar[Dict[CuratedFile, str]]): The prefix of the sections of the records of each file.
        directory (Path): The bundle directory.
        logger (Logger): The files logger.

    Notes:
        - The bundle is the reviewed copy of the curated data: it seeds a fresh database (`migrate-db seed`) and is
          written back by `curated export`, so that the edits made in the explorer are kept in git.
        - The files list the rows in a canonical order (`_sorted`), their keys sorted and a row's default values left
          out, so that an export of the database gives the same files as the bundle it was seeded from, and a change
          reads as a small diff.
    """

    FIELDS: ClassVar[Dict[CuratedFile, List[Tuple[str, str]]]] = {
        CuratedFile.CHRONOLOGY: [("records", "records")],
        CuratedFile.MARKETS: [("records", "records")],
        CuratedFile.COMPANIES: [("profiles", "profiles"), ("identifiers", "identifiers")],
        CuratedFile.FIGURES: [
            ("companies", "figure_companies"),
            ("years", "figure_years"),
            ("events", "figure_events"),
        ],
        CuratedFile.LAUNCHES: [("launches", "launches"), ("records", "records")],
    }
    PREFIXES: ClassVar[Dict[CuratedFile, str]] = {
        CuratedFile.CHRONOLOGY: "chronology-",
        CuratedFile.MARKETS: "markets-",
        CuratedFile.LAUNCHES: "launch-",
    }

    def __init__(self, directory: Path = CURATED_DIR, logger: Optional[Logger] = None) -> None:
        """Initialize the files.

        Args:
            directory (Path): The bundle directory, `data/curated` by default.
            logger (Optional[Logger]): The files logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.directory = directory

    ############################
    # Internal Helpers Methods #
    ############################

    def _path(self, file: CuratedFile) -> Path:
        """Get the path of a bundle file.

        Args:
            file (CuratedFile): The file.

        Returns:
            Path: Its path.
        """
        return self.directory / f"{file.value}.json"

    def _sorted(self, bundle: CuratedBundle) -> CuratedBundle:
        """Put the rows of a bundle in their canonical order, whichever order they were read in.

        Args:
            bundle (CuratedBundle): The bundle.

        Returns:
            CuratedBundle: The same rows: the records by section (in the order of `CuratedDataset`) and rank, the
                rows of a company by company and rank, the others by rank.
        """
        datasets, kinds = list(CuratedDataset), list(IdentifierKind)
        return bundle.model_copy(
            update={
                "records": sorted(bundle.records, key=lambda row: (datasets.index(row.dataset), row.position, row.key)),
                "profiles": sorted(bundle.profiles, key=lambda row: (row.position, row.company)),
                "identifiers": sorted(
                    bundle.identifiers, key=lambda row: (row.company, kinds.index(row.kind), row.position, row.value)
                ),
                "figure_companies": sorted(bundle.figure_companies, key=lambda row: (row.position, row.company)),
                "figure_years": sorted(
                    bundle.figure_years, key=lambda row: (row.company, row.position, row.fiscal_year)
                ),
                "figure_events": sorted(bundle.figure_events, key=lambda row: (row.company, row.position)),
                "launches": sorted(bundle.launches, key=lambda row: (row.position, row.crawler, row.name)),
            }
        )

    def _content(self, bundle: CuratedBundle, file: CuratedFile) -> Dict[str, JsonValue]:
        """Get what a bundle file holds.

        Args:
            bundle (CuratedBundle): The bundle.
            file (CuratedFile): The file.

        Returns:
            Dict[str, JsonValue]: Its lists, each row without its default values.
        """
        dumped = bundle.model_dump(mode="json", exclude_defaults=True)
        content: Dict[str, JsonValue] = {}
        for key, field in self.FIELDS[file]:
            rows = dumped.get(field, [])
            if field == "records":
                prefix = self.PREFIXES[file]
                rows = [row for row in rows if isinstance(row, dict) and str(row.get("dataset", "")).startswith(prefix)]
            content[key] = rows
        return content

    ############################
    # Publicly Exposed Methods #
    ############################

    def part(self, bundle: CuratedBundle, file: CuratedFile) -> CuratedBundle:
        """Get the rows of a bundle file.

        Args:
            bundle (CuratedBundle): The whole bundle.
            file (CuratedFile): The file.

        Returns:
            CuratedBundle: Its rows only.
        """
        content = self._content(bundle, file)
        return CuratedBundle.model_validate({field: content[key] for key, field in self.FIELDS[file]})

    def write(self, bundle: CuratedBundle) -> List[Path]:
        """Write the bundle, a file per catalogue.

        Args:
            bundle (CuratedBundle): The bundle.

        Returns:
            List[Path]: The files written.

        Raises:
            CuratedBundleError: If a file cannot be written.
        """
        written: List[Path] = []
        ordered = self._sorted(bundle)
        for file in CuratedFile:
            path = self._path(file)
            text = json.dumps(self._content(ordered, file), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            except OSError as e:
                self.logger.error("The curated bundle file %s cannot be written: %s", path, e.strerror)
                raise CuratedBundleError(str(path), f"the file cannot be written ({e.strerror}).") from e
            written.append(path)
        self.logger.info("Curated bundle written: %d files in %s.", len(written), self.directory)
        return written

    def read(self, file: Optional[CuratedFile] = None) -> CuratedBundle:
        """Read the bundle, or one of its files.

        Args:
            file (Optional[CuratedFile]): The file read, every one when `None`.

        Returns:
            CuratedBundle: The rows.

        Raises:
            CuratedBundleError: If a file cannot be read, is not valid JSON or is invalid.
        """
        merged: Dict[str, List[JsonValue]] = {}
        for current in [file] if file else list(CuratedFile):
            path = self._path(current)
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except OSError as e:
                self.logger.error("The curated bundle file %s cannot be read: %s", path, e.strerror)
                raise CuratedBundleError(str(path), f"the file cannot be read ({e.strerror}).") from e
            except ValueError as e:
                self.logger.error("The curated bundle file %s is not valid JSON.", path)
                raise CuratedBundleError(str(path), f"the file is not valid JSON ({e}).") from e
            for key, field in self.FIELDS[current]:
                rows = content.get(key, []) if isinstance(content, dict) else []
                merged.setdefault(field, []).extend(rows if isinstance(rows, list) else [])
        try:
            bundle = CuratedBundle.model_validate(merged)
        except ValidationError as e:
            self.logger.error("The curated bundle in %s is invalid (%d errors).", self.directory, e.error_count())
            raise CuratedBundleError(str(self.directory), f"the rows are invalid.\n{e}") from e
        self.logger.debug("Curated bundle read: %d records, %d launches.", len(bundle.records), len(bundle.launches))
        return bundle

    def hashes(self) -> Dict[CuratedFile, str]:
        """Get the hash of each bundle file (a seed applies only the files that changed).

        Returns:
            Dict[CuratedFile, str]: The SHA-256 of each file present, by file.
        """
        found = {
            file: hashlib.sha256(self._path(file).read_bytes()).hexdigest()
            for file in CuratedFile
            if self._path(file).is_file()
        }
        self.logger.debug("Hashes of %d curated bundle files.", len(found))
        return found
