from __future__ import annotations

# Standard Library Imports.
import argparse
import asyncio
import json
import sys
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from pydantic import BaseModel

# First Party Imports.
from conf import CURATED_DIR
from curated.bundle.bundle_files import BundleFiles
from curated.exception import CuratedError
from logger import setup_logging
from models.configuration.storage.storage_settings import StorageSettings
from models.curated.enums import CuratedFile
from models.curated.records.curated_bundle import CuratedBundle
from scripts.enums import CuratedCommand
from storage.exception import StorageError
from storage.storage import Storage


class CuratedCli:
    """The `curated` command: write the curated bundle, apply it to the database, or compare them.

    Attributes:
        settings (Optional[StorageSettings]): The storage settings, read from the environment when `None`.
        logger (Logger): The command logger.

    Notes:
        - `export` writes the bundle from the database (the edits made in the explorer, to commit), `import`
          applies the bundle files that changed (as `migrate-db seed` does), `diff` counts the rows the database and
          the bundle do not share.
        - The bundle is `data/curated/*.json` unless `--dir` names another directory.
    """

    def __init__(self, settings: Optional[StorageSettings] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the command.

        Args:
            settings (Optional[StorageSettings]): The storage settings, read from the environment by default.
            logger (Optional[Logger]): The command logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.settings = settings

    ############################
    # Internal Helpers Methods #
    ############################

    def _arguments(self, argv: Optional[Sequence[str]]) -> argparse.Namespace:
        """Parse the arguments.

        Args:
            argv (Optional[Sequence[str]]): The arguments.

        Returns:
            argparse.Namespace: The command and its options.
        """
        parser = argparse.ArgumentParser(prog="curated", description="Move the curated catalogues in and out.")
        commands = parser.add_subparsers(dest="command", required=True)
        for command, help_text in (
            (CuratedCommand.EXPORT, "write the bundle from the database"),
            (CuratedCommand.IMPORT, "apply the bundle to the database"),
            (CuratedCommand.DIFF, "count the rows the database and the bundle do not share"),
        ):
            sub = commands.add_parser(command.value, help=help_text)
            sub.add_argument("--dir", type=Path, default=CURATED_DIR, help="the bundle directory")
            if command is CuratedCommand.IMPORT:
                sub.add_argument("--force", action="store_true", help="apply the files even when unchanged")
                sub.add_argument("--replace-edited", action="store_true", help="replace the rows a person changed")
        return parser.parse_args(argv)

    def _storage(self) -> Storage:
        """Get a storage of the settings.

        Returns:
            Storage: The storage, not open yet.
        """
        return Storage(self.settings) if self.settings else Storage()

    async def _export(self, directory: Path) -> List[Path]:
        """Write the bundle from the database.

        Args:
            directory (Path): The bundle directory.

        Returns:
            List[Path]: The files written.
        """
        async with self._storage() as storage:
            bundle = await storage.catalogs.bundle()
        return BundleFiles(directory, self.logger).write(bundle)

    async def _import(self, directory: Path, force: bool, replace_edited: bool) -> Dict[CuratedFile, Tuple[int, int]]:
        """Apply the bundle to the database.

        Args:
            directory (Path): The bundle directory.
            force (bool): Whether the files are applied even when unchanged.
            replace_edited (bool): Whether the rows a person changed are replaced too.

        Returns:
            Dict[CuratedFile, Tuple[int, int]]: The rows written and kept of each file applied.
        """
        async with self._storage() as storage:
            return await storage.curated_seeder.seed(BundleFiles(directory, self.logger), force, replace_edited)

    def _canonical(self, row: BaseModel) -> str:
        """Write a row as canonical JSON, to compare a stored row with a bundled one.

        Args:
            row (BaseModel): The row.

        Returns:
            str: Its JSON, keys sorted (the database reorders the keys of a JSON body), its origin and whether a
                person changed it left out.
        """
        return json.dumps(row.model_dump(mode="json", exclude={"origin", "edited"}), sort_keys=True)

    async def _diff(self, directory: Path) -> Dict[str, Tuple[int, int]]:
        """Count the rows the database and the bundle do not share.

        Args:
            directory (Path): The bundle directory.

        Returns:
            Dict[str, Tuple[int, int]]: For each kind of row, the rows only in the database, then those only in the
                bundle or different.
        """
        async with self._storage() as storage:
            stored = await storage.catalogs.bundle()
        written = BundleFiles(directory, self.logger).read()
        counts: Dict[str, Tuple[int, int]] = {}
        for field in CuratedBundle.model_fields:
            ours = {self._canonical(item) for item in getattr(stored, field)}
            theirs = {self._canonical(item) for item in getattr(written, field)}
            counts[field] = (len(ours - theirs), len(theirs - ours))
        return counts

    ############################
    # Publicly Exposed Methods #
    ############################

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run a command of the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when the command failed (logged).
        """
        arguments = self._arguments(argv)
        directory: Path = arguments.dir
        try:
            match CuratedCommand(arguments.command):
                case CuratedCommand.EXPORT:
                    for path in asyncio.run(self._export(directory)):
                        print(path)
                case CuratedCommand.IMPORT:
                    applied = asyncio.run(self._import(directory, arguments.force, arguments.replace_edited))
                    for file, (written, kept) in applied.items():
                        print(f"{file.value}: {written} rows written, {kept} changed by a person kept")
                    if not applied:
                        print("the database is up to date")
                case CuratedCommand.DIFF:
                    for field, (stored, written) in asyncio.run(self._diff(directory)).items():
                        print(f"{field}: {stored} only in the database, {written} only in the bundle or different")
        except (CuratedError, StorageError) as e:
            self.logger.error("The curated command failed: %s", e)
            return 1
        return 0


def main() -> int:
    """Console entry point of `uv run curated`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return CuratedCli().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
