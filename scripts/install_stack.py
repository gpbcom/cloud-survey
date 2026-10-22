from __future__ import annotations

# Standard Library Imports.
import argparse
import asyncio
import shutil
import sys
import time
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, List, Optional, Sequence

# First Party Imports.
from logger import setup_logging
from models.configuration.storage.storage_settings import StorageSettings
from scripts.enums import ComposeService
from scripts.exception import MigrationError, StackInstallError
from scripts.migrate_database import DatabaseMigrator
from storage.engine.database import Database
from storage.engine.settings_reader import StorageSettingsReader
from storage.exception import StorageError
from storage.importer.json_importer import JsonImporter
from storage.storage import Storage


class StackInstaller:
    """Install the storage stack of the crawler: `uv run install-stack`.

    Attributes:
        PROJECT_DIR (ClassVar[Path]): The project folder, holding `compose.yaml`.
        TEST_URL (ClassVar[str]): The URL of the test database.
        WAIT_TIMEOUT (ClassVar[float]): How long, in seconds, the database may take to accept connections.
        WAIT_DELAY (ClassVar[float]): The delay, in seconds, between two connection attempts.
        logger (Logger): The installer logger.

    Notes:
        The steps, each idempotent (running it again changes nothing):
        1. Start the PostgreSQL server with Docker Compose (`compose.yaml`), unless `--no-docker`.
        2. Wait until the database accepts connections.
        3. Apply the database migrations.
        4. Optionally import the JSON files of the former file storage (`--import-json`).
    """

    PROJECT_DIR: ClassVar[Path] = Path(__file__).parent.parent
    TEST_URL: ClassVar[str] = "postgresql+asyncpg://crawler:crawler@localhost:5433/poc_crawler_test"
    WAIT_TIMEOUT: ClassVar[float] = 60.0
    WAIT_DELAY: ClassVar[float] = 1.0

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the installer.

        Args:
            logger (Optional[Logger]): The installer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Stack installer of %s ready.", self.PROJECT_DIR)

    ############################
    # Internal Helpers Methods #
    ############################

    def _arguments(self, argv: Optional[Sequence[str]]) -> argparse.Namespace:
        """Parse the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            argparse.Namespace: The options.
        """
        self.logger.debug("Parsing the command line %s.", list(argv) if argv is not None else sys.argv[1:])
        parser = argparse.ArgumentParser(prog="install-stack", description="Install the crawler storage stack.")
        parser.add_argument("--no-docker", action="store_true", help="use the server of CRAWLER_DATABASE_URL")
        parser.add_argument("--test", action="store_true", help="also start and migrate the test database")
        parser.add_argument(
            "--import-json",
            nargs="?",
            const="output",
            default=None,
            metavar="FOLDER",
            help="import the JSON files of the former file storage (output/ by default)",
        )
        parser.add_argument("--replace", action="store_true", help="replace the stored datasets when importing")
        return parser.parse_args(argv)

    async def _run(self, command: List[str]) -> str:
        """Run a command in the project folder.

        Args:
            command (List[str]): The command and its arguments.

        Returns:
            str: Its standard output.

        Raises:
            StackInstallError: If the command cannot be run or fails.
        """
        self.logger.debug("Running %s.", " ".join(command))
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.PROJECT_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, errors = await process.communicate()
        except OSError as e:
            self.logger.error("%s cannot be run: %s", command[0], e)
            raise StackInstallError(" ".join(command), str(e)) from e
        if process.returncode != 0:
            reason = errors.decode("utf-8", "replace").strip() or f"exit code {process.returncode}"
            self.logger.error("%s failed: %s", " ".join(command), reason)
            raise StackInstallError(" ".join(command), reason)
        return output.decode("utf-8", "replace")

    async def _start_services(self, services: List[ComposeService]) -> None:
        """Start the database servers with Docker Compose, waiting for them to be healthy.

        Args:
            services (List[ComposeService]): The Compose services.

        Raises:
            StackInstallError: If Docker Compose is missing or cannot start the services.
        """
        if not shutil.which("docker"):
            self.logger.error("Docker is not installed.")
            raise StackInstallError(
                "docker",
                "Docker is not installed: install it (https://docs.docker.com/engine/install/) or use --no-docker",
            )
        await self._run(["docker", "compose", "version"])
        self.logger.info("Starting %s with Docker Compose.", ", ".join(services))
        await self._run(["docker", "compose", "--profile", "test", "up", "-d", "--wait", *services])
        self.logger.info("%s running.", ", ".join(services))

    async def _wait(self, settings: StorageSettings) -> None:
        """Wait until a database accepts connections.

        Args:
            settings (StorageSettings): The settings of the database.

        Raises:
            StackInstallError: If the database still refuses connections after `WAIT_TIMEOUT` seconds.
        """
        database = Database(settings, self.logger)
        deadline = time.monotonic() + self.WAIT_TIMEOUT
        while True:
            try:
                await database.open(check_schema=False)
                await database.close()
                return
            except StorageError as e:
                if time.monotonic() >= deadline:
                    self.logger.error("The database %s still refuses connections: %s", database.url, e)
                    raise StackInstallError("wait for the database", str(e)) from e
                self.logger.debug("The database %s is not ready yet: %s", database.url, e)
                await asyncio.sleep(self.WAIT_DELAY)

    async def _migrate(self, settings: StorageSettings) -> None:
        """Apply the migrations of a database, in a thread (Alembic runs its own event loop).

        Args:
            settings (StorageSettings): The settings of the database.

        Raises:
            StackInstallError: If the migrations cannot be applied.
        """
        try:
            await asyncio.to_thread(DatabaseMigrator(settings, self.logger).upgrade)
        except MigrationError as e:
            self.logger.error("The migrations cannot be applied: %s", e)
            raise StackInstallError("migrate the database", e.reason) from e

    async def _import(self, settings: StorageSettings, folder: Path, replace: bool) -> None:
        """Import the JSON files of the former file storage.

        Args:
            settings (StorageSettings): The settings of the database.
            folder (Path): The output folder of the former file storage.
            replace (bool): Whether the stored datasets are replaced.

        Raises:
            StackInstallError: If the folder does not exist or the storage cannot be opened.
        """
        if not folder.is_dir():
            self.logger.error("The folder %s to import does not exist.", folder)
            raise StackInstallError("import the JSON files", f"{folder} is not a folder")
        try:
            async with Storage(settings, self.logger) as storage:
                imported = await JsonImporter(storage, self.logger).import_folder(folder, replace)
        except StorageError as e:
            self.logger.error("The JSON files cannot be imported: %s", e)
            raise StackInstallError("import the JSON files", str(e)) from e
        for name, count in imported.items():
            print(f"{name}: {count} items")

    async def _install(self, arguments: argparse.Namespace) -> None:
        """Run the installation steps.

        Args:
            arguments (argparse.Namespace): The command line options.

        Raises:
            StackInstallError: If a step fails.
        """
        self.logger.info(
            "Installing the storage stack (docker: %s, test database: %s, import: %s).",
            not arguments.no_docker,
            arguments.test,
            arguments.import_json,
        )
        reader = StorageSettingsReader(self.logger)
        settings = reader.read()
        databases = [settings]
        if arguments.test:
            databases.append(settings.model_copy(update={"url": self.TEST_URL}))
        if not arguments.no_docker:
            services = (
                [ComposeService.POSTGRES, ComposeService.POSTGRES_TEST] if arguments.test else [ComposeService.POSTGRES]
            )
            await self._start_services(services)
        for database in databases:
            await self._wait(database)
            await self._migrate(database)
        if arguments.import_json is not None:
            await self._import(settings, Path(arguments.import_json), arguments.replace)
        print(f"The storage is ready at {reader.safe_url(settings.url)} (CRAWLER_DATABASE_URL).")
        if arguments.test:
            print(f"The test database is ready at {reader.safe_url(self.TEST_URL)} (STORAGE_TEST_DATABASE_URL).")

    ############################
    # Publicly Exposed Methods #
    ############################

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Install the stack from the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when a step failed (logged).
        """
        arguments = self._arguments(argv)
        try:
            asyncio.run(self._install(arguments))
        except StackInstallError as e:
            self.logger.error("%s", e)
            return 1
        self.logger.info("The storage stack is installed.")
        return 0


def main() -> int:
    """Console entry point of `uv run install-stack`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return StackInstaller().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
