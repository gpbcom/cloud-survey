from __future__ import annotations

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Boolean, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class UsageProfileRow(Base):
    """A workload whose monthly cost is compared across the providers (see `UsageProfile`).

    Attributes:
        name (Mapped[str]): The name of the profile.
        description (Mapped[str]): What workload it stands for.
        items (Mapped[JsonValue]): Its consumptions per month, as JSON.
        origin (Mapped[str]): Who wrote it.
        edited (Mapped[bool]): Whether a person changed it.
    """

    __tablename__ = StorageTable.USAGE_PROFILES

    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    items: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    origin: Mapped[str] = mapped_column(String(12), server_default="user")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
