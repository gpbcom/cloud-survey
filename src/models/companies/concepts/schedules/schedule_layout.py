from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.concepts.schedules.schedule_tag import ScheduleTag
from models.companies.exception import DuplicateCompanyKeyError
from models.markets.field_check import MarketFieldCheck


class ScheduleLayout(BaseModel):
    """How the SEC financial data schedules (EX-27, filed from 1993 to 2001) are read.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        articles (List[int]): The articles of Regulation S-X read (5: the commercial and industrial companies, the
            banks' article 9 and the insurers' article 7 having other tags).
        tags (List[ScheduleTag]): The tags read, each once.

    Notes:
        A schedule states the balance at the end of the period and the flows since its start: no research expense,
        no operating income, no cash flow. Its `DEPRECIATION` and `PP&E` are balance-sheet amounts (the accumulated
        depreciation), never the depreciation of the period: they are not read.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    articles: List[int] = Field(default_factory=lambda: [5], description="The articles of Regulation S-X read.")
    tags: List[ScheduleTag] = Field(default_factory=list, description="The tags read.")

    @field_validator("articles", mode="before")
    def validate_articles(cls, value: JsonValue) -> JsonValue:
        """Validate the raw articles: a list of whole numbers from 1 to 12.

        Args:
            value (JsonValue): The raw articles.

        Returns:
            JsonValue: The articles.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketNumberError: If an article is not a whole number from 1 to 12.
        """
        items = cls.CHECK.items(value, "schedule articles", "numbers")
        return [cls.CHECK.number(item, "schedule article", low=1, high=12, integer=True) for item in items]

    @field_validator("tags", mode="before")
    def validate_tags(cls, value: JsonValue) -> JsonValue:
        """Validate the raw tags: a list, each tag once.

        Args:
            value (JsonValue): The raw tags.

        Returns:
            JsonValue: The tags (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a tag is defined twice.
        """
        items = cls.CHECK.items(value, "schedule tags", "mappings of tag and metric")
        seen: List[str] = []
        for item in items:
            tag = item.get("tag") if isinstance(item, dict) else None
            if isinstance(tag, str):
                if tag in seen:
                    raise DuplicateCompanyKeyError("schedule tag", tag)
                seen.append(tag)
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def by_tag(self) -> Dict[str, ScheduleTag]:
        """Get the definition of each tag read.

        Returns:
            Dict[str, ScheduleTag]: The definition of each tag.
        """
        return {tag.tag: tag for tag in self.tags}

    def find(self, tag: str) -> Optional[ScheduleTag]:
        """Get the definition of a tag.

        Args:
            tag (str): The tag, as the schedule writes it.

        Returns:
            Optional[ScheduleTag]: Its definition, `None` when it is not read.
        """
        return next((item for item in self.tags if item.tag == tag.strip().upper()), None)
