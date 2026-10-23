from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import ShareSource
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class PressFamily(BaseModel):
    """A family of analyst press releases giving the shares of a segment in an area, e.g. IDC's worldwide PCs.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a segment key: lower-case words joined by hyphens.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        source (ShareSource): The firm publishing the releases.
        segment (str): The segment their shares belong to.
        area (str): The area of their shares, e.g. `ww` or `IN`.
        pattern (str): The regular expression a release must match (case-insensitive), on its title and the caption
            of its table joined by ` | `.
        exclude (Optional[str]): A regular expression a release must not match, e.g. the used or foldable phones.
        search (Optional[str]): The search term listing the releases, at a firm whose releases are searched (IDC).

    Notes:
        A release matching several families goes to the first one,
        in the catalogue order: list the narrow
        families (a country) before the broad ones (worldwide).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: ShareSource = Field(description="The firm publishing the releases.")
    segment: str = Field(description="The segment of their shares.")
    area: str = Field(default="ww", min_length=2, max_length=12, description="The area of their shares.")
    pattern: str = Field(min_length=1, description="The regular expression a release must match.")
    exclude: Optional[str] = Field(default=None, description="The regular expression a release must not match.")
    search: Optional[str] = Field(default=None, max_length=80, description="The search term listing the releases.")

    @field_validator("segment", mode="before")
    def validate_segment(cls, value: JsonValue) -> JsonValue:
        """Validate the raw segment: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw segment.

        Returns:
            JsonValue: The segment, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "release segment", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("segment key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw firm: a `ShareSource` value.

        Args:
            value (JsonValue): The raw firm.

        Returns:
            JsonValue: The firm.

        Raises:
            InvalidMarketChoiceError: If it is not a known share source.
        """
        return cls.CHECK.choice(value, "release firm", [source.value for source in ShareSource])

    @field_validator("area", mode="before")
    def validate_area(cls, value: JsonValue) -> JsonValue:
        """Validate the raw area: a text of 2 to 12 characters.

        Args:
            value (JsonValue): The raw area.

        Returns:
            JsonValue: The area, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 2 to 12 characters.
        """
        return cls.CHECK.text(value, "release area", 12, minimum=2)

    @field_validator("search", mode="before")
    def validate_search(cls, value: JsonValue) -> JsonValue:
        """Validate the raw search term: a text of at most 80 characters, `None` when missing.

        Args:
            value (JsonValue): The raw term.

        Returns:
            JsonValue: The term.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 80 characters.
        """
        return cls.CHECK.text(value, "release search term", 80, optional=True)

    @field_validator("pattern", "exclude", mode="before")
    def validate_pattern(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw regular expression: it compiles (the exclusion may be missing).

        Args:
            value (JsonValue): The raw expression.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The expression.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it does not compile.
        """
        value = cls.CHECK.text(
            value, f"release {info.field_name}", 1000, optional=info.field_name == "exclude", collapse=False
        )
        if value is None:
            return None
        try:
            re.compile(value)
        except re.error as e:
            raise InvalidMarketValueError("release pattern", value, f"a valid regular expression ({e})") from e
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def matches(self, text: str) -> bool:
        """Tell whether a release belongs to the family.

        Args:
            text (str): The release title and its table caption, joined by ` | `.

        Returns:
            bool: Whether it matches the pattern and not the exclusion.
        """
        if not re.search(self.pattern, text, re.IGNORECASE):
            return False
        return not (self.exclude and re.search(self.exclude, text, re.IGNORECASE))
