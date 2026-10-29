from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.compounding.exception import DuplicateCompoundingEntryError
from models.compounding.help.help_entry import HelpEntry
from models.markets.field_check import MarketFieldCheck


class CompoundingHelp(BaseModel):
    """The explanations of the Service compounding section, shown in its tooltips.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        controls (List[HelpEntry]): The controls (`CompoundingControl`).
        choices (List[HelpEntry]): The choices of the pickers (`Specification`, `FoundationSource` values).
        columns (List[HelpEntry]): The columns of the tables (`CompoundingColumn`).
        warnings (List[HelpEntry]): The caveats (`CompoundingWarningKind`).
        verdicts (List[HelpEntry]): The verdicts (`Verdict`).
        curves (List[HelpEntry]): The growth curves (`CurveKind`).
        cards (List[HelpEntry]): The cards (`CompoundingCard`).

    Notes:
        The file is the `compounding` block of `conf/help.yaml`. A test checks that every enum value is explained.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    controls: List[HelpEntry] = Field(default_factory=list, description="The controls.")
    choices: List[HelpEntry] = Field(default_factory=list, description="The choices of the pickers.")
    columns: List[HelpEntry] = Field(default_factory=list, description="The columns of the tables.")
    warnings: List[HelpEntry] = Field(default_factory=list, description="The caveats.")
    verdicts: List[HelpEntry] = Field(default_factory=list, description="The verdicts.")
    curves: List[HelpEntry] = Field(default_factory=list, description="The growth curves.")
    cards: List[HelpEntry] = Field(default_factory=list, description="The cards.")

    @field_validator("controls", "choices", "columns", "warnings", "verdicts", "curves", "cards", mode="before")
    def validate_entries(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw entries: a list, each key once.

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a key is explained twice.
        """
        items = cls.CHECK.items(value, f"{info.field_name} help", "mappings with a key, a title and a text")
        seen: List[str] = []
        for item in items:
            key = item.get("key") if isinstance(item, dict) else None
            if isinstance(key, str):
                if key in seen:
                    raise DuplicateCompoundingEntryError(f"{info.field_name} help", key)
                seen.append(key)
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def entry(self, group: str, key: str) -> Optional[HelpEntry]:
        """Get an explanation.

        Args:
            group (str): The group (`controls`, `choices`, `columns`, `warnings`, `verdicts`, `curves`, `cards`).
            key (str): What is explained.

        Returns:
            Optional[HelpEntry]: The explanation, `None` when there is none.
        """
        entries: List[HelpEntry] = getattr(self, group, [])
        return next((entry for entry in entries if entry.key == key), None)

    def text(self, group: str, key: str) -> str:
        """Get the text of an explanation.

        Args:
            group (str): The group.
            key (str): What is explained.

        Returns:
            str: The text, empty when there is none.
        """
        found = self.entry(group, key)
        return found.text if found else ""

    def title(self, group: str, key: str) -> str:
        """Get the title of an explanation.

        Args:
            group (str): The group.
            key (str): What is explained.

        Returns:
            str: The title, the key itself when there is none.
        """
        found = self.entry(group, key)
        return found.title if found else key
