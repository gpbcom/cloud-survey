from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class StorageSettings(BaseModel):
    """The settings of the PostgreSQL storage of the crawled data.

    Attributes:
        url (str): The SQLAlchemy URL of the database, with the asyncpg driver
            (`postgresql+asyncpg://user:password@host:port/database`).
        pool_size (int): The number of connections kept open.
        max_overflow (int): The number of connections opened on top of `pool_size` under load (each running crawl
            holds one connection).
        batch_size (int): The number of crawled items written per statement batch.
        echo (bool): Whether every SQL statement is logged (debugging).
        command_timeout_s (float): The longest a statement may run, in seconds (raised by the price crawl for its
            large merges).
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(
        default="postgresql+asyncpg://crawler:crawler@localhost:5432/poc_crawler",
        pattern=r"^postgresql\+asyncpg://",
        description="The SQLAlchemy URL of the database, with the asyncpg driver.",
    )
    pool_size: int = Field(default=5, ge=1, le=100, description="The number of connections kept open.")
    max_overflow: int = Field(default=30, ge=0, le=500, description="The extra connections opened under load.")
    batch_size: int = Field(default=2000, ge=1, le=50_000, description="The items written per statement batch.")
    echo: bool = Field(default=False, description="Whether every SQL statement is logged.")
    command_timeout_s: float = Field(default=300.0, gt=0, le=7200, description="The longest a statement may run.")
