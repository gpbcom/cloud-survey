from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class MigrationCommand(StrEnum):
    """Enums representing the commands of `uv run migrate-db`.

    Attributes:
        UPGRADE (str): Apply the migrations up to a revision.
        DOWNGRADE (str): Revert the migrations down to a revision.
        CURRENT (str): Show the revision of the database.
        HISTORY (str): List the migrations.
        REVISION (str): Write a new migration.
        CHECK (str): Fail when the tables and the database schema differ.
        SEED (str): Apply the seed of the unified taxonomy (domains, categories, source labels).
    """

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    CURRENT = "current"
    HISTORY = "history"
    REVISION = "revision"
    CHECK = "check"
    SEED = "seed"


@unique
class ComposeService(StrEnum):
    """Enums representing the Docker Compose services of `compose.yaml`.

    Attributes:
        POSTGRES (str): The database of the crawled data.
        POSTGRES_TEST (str): The throw-away database of the tests.
    """

    POSTGRES = "postgres"
    POSTGRES_TEST = "postgres-test"


class CuratedCommand(StrEnum):
    """Enums representing the commands of `uv run curated`.

    Attributes:
        EXPORT (str): Write the bundle from the database (the edits made in the explorer).
        IMPORT (str): Apply the bundle to the database (the files that changed).
        DIFF (str): Count the rows the database and the bundle do not share.
    """

    EXPORT = "export"
    IMPORT = "import"
    DIFF = "diff"
