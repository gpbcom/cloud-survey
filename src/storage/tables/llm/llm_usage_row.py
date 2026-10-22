from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from decimal import Decimal

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class LlmUsageRow(Base):
    """A call to the language model: the task, the model, its tokens and its cost.

    Attributes:
        id (Mapped[int]): The call identifier.
        task (Mapped[str]): The task of the call (e.g. `label_translation`).
        provider (Mapped[str]): The model provider (e.g. `anthropic`).
        model (Mapped[str]): The model name.
        input_tokens (Mapped[int]): The input tokens, cached ones excluded.
        output_tokens (Mapped[int]): The output tokens.
        cache_read_tokens (Mapped[int]): The input tokens read from the prompt cache.
        cache_write_tokens (Mapped[int]): The input tokens written to the prompt cache.
        cost (Mapped[Decimal]): The cost of the call.
        currency (Mapped[str]): The currency of the cost (ISO 4217).
        called_at (Mapped[datetime]): When the call was made.

    Notes:
        The budget ceiling is checked against the sum of the costs before every call.
    """

    __tablename__ = StorageTable.LLM_USAGE
    __table_args__ = (Index("ix_llm_usage_called_at", "called_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    task: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
