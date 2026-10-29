from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, date, datetime
from typing import ClassVar, Optional, Pattern, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

# First Party Imports.
from models.cloud.enums import LaunchPrecision, UrlScheme
from models.cloud.exception import InvalidLaunchFieldError, MissingLaunchReasonError, MissingLaunchSourceError


class CuratedLaunch(BaseModel):
    """The launch of a catalogue product, read by hand from a cited announcement.

    Attributes:
        CRAWLER (ClassVar[Pattern[str]]): The format of a crawler name: lower-case words joined by hyphens.
        LAUNCHED (ClassVar[Pattern[str]]): The format of a launch: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        NAME_LIMIT (ClassVar[int]): The longest product name.
        REASON_LIMIT (ClassVar[int]): The longest reason.
        EARLIEST_YEAR (ClassVar[int]): The earliest plausible launch year.
        crawler (str): The crawler of the product, e.g. `gcp`.
        name (str): The product, as the catalogue names it.
        launched (Optional[str]): The launch, as precise as the source gives it, `None` when no source was found.
        source (Optional[str]): The announcement it is read from, an absolute http(s) link.
        reason (Optional[str]): Why the product has no launch date, when it has none.

    Notes:
        - The launch is the first public availability (preview or general availability, whichever is earlier), as
          the provider's updates and release notes date it.
        - A product listed without a launch is a known gap: the crawl leaves it undated without reporting it.
    """

    CRAWLER: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    LAUNCHED: ClassVar[Pattern[str]] = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    NAME_LIMIT: ClassVar[int] = 120
    REASON_LIMIT: ClassVar[int] = 300
    EARLIEST_YEAR: ClassVar[int] = 1990

    model_config = ConfigDict(frozen=True, extra="forbid")

    crawler: str = Field(description="The crawler of the product.")
    name: str = Field(description="The product, as the catalogue names it.")
    launched: Optional[str] = Field(default=None, description="The launch: YYYY, YYYY-MM or YYYY-MM-DD.")
    source: Optional[str] = Field(default=None, description="The announcement the launch is read from.")
    reason: Optional[str] = Field(default=None, description="Why the product has no launch date.")

    @field_validator("crawler", mode="before")
    def validate_crawler(cls, value: JsonValue) -> JsonValue:
        """Validate the raw crawler name: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw crawler name.

        Returns:
            JsonValue: The crawler name, trimmed.

        Raises:
            InvalidLaunchFieldError: If it is not lower-case words joined by hyphens.
        """
        crawler = value.strip() if isinstance(value, str) else ""
        if not cls.CRAWLER.match(crawler):
            raise InvalidLaunchFieldError("crawler", str(value), "lower-case words joined by hyphens")
        return crawler

    @field_validator("name", mode="before")
    def validate_name(cls, value: JsonValue) -> JsonValue:
        """Validate the raw product name: a text of 1 to 120 characters, spaces collapsed.

        Args:
            value (JsonValue): The raw product name.

        Returns:
            JsonValue: The product name.

        Raises:
            InvalidLaunchFieldError: If it is not a text of 1 to 120 characters.
        """
        name = " ".join(value.split()) if isinstance(value, str) else ""
        if not 0 < len(name) <= cls.NAME_LIMIT:
            raise InvalidLaunchFieldError("product name", str(value), f"a text of 1 to {cls.NAME_LIMIT} characters")
        return name

    @field_validator("launched", mode="before")
    def validate_launched(cls, value: Union[JsonValue, date]) -> JsonValue:
        """Validate the raw launch: a year, a month or a day, from 1990 to today.

        Args:
            value (Union[JsonValue, date]): The raw launch, a text, a year number or a date (YAML reads an unquoted day
                as a date).

        Returns:
            JsonValue: The launch as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, `None` when missing.

        Raises:
            InvalidLaunchFieldError: If it is not a plausible year, month or day.
        """
        if value is None:
            return None
        launched = value.isoformat() if isinstance(value, date) else str(value).strip()
        if not cls.LAUNCHED.match(launched):
            raise InvalidLaunchFieldError("date", launched, "a year, a month or a day (YYYY, YYYY-MM, YYYY-MM-DD)")
        parts = [int(part) for part in launched.split("-")]
        try:
            day = date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        except ValueError as e:
            raise InvalidLaunchFieldError("date", launched, "an existing year, month or day") from e
        if day.year < cls.EARLIEST_YEAR or day > datetime.now(UTC).date():
            raise InvalidLaunchFieldError("date", launched, f"from {cls.EARLIEST_YEAR} to today")
        return launched

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: an absolute http(s) link.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The link, trimmed, `None` when missing or blank.

        Raises:
            InvalidLaunchFieldError: If it is not an absolute http(s) link.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        link = urlparse(value.strip()) if isinstance(value, str) else None
        if link is None or link.scheme not in tuple(UrlScheme) or not link.netloc:
            raise InvalidLaunchFieldError("source", str(value), "an absolute http(s) link")
        return link.geturl()

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: JsonValue) -> JsonValue:
        """Validate the raw reason: a text of up to 300 characters, spaces collapsed.

        Args:
            value (JsonValue): The raw reason.

        Returns:
            JsonValue: The reason, `None` when missing or blank.

        Raises:
            InvalidLaunchFieldError: If it is not a text of up to 300 characters.
        """
        if value is None:
            return None
        reason = " ".join(value.split()) if isinstance(value, str) else None
        if reason is None or len(reason) > cls.REASON_LIMIT:
            raise InvalidLaunchFieldError("reason", str(value), f"a text of up to {cls.REASON_LIMIT} characters")
        return reason or None

    @model_validator(mode="after")
    def validate_evidence(self) -> CuratedLaunch:
        """Check that a launch cites its source, and that a product without launch says why.

        Returns:
            CuratedLaunch: The launch.

        Raises:
            MissingLaunchSourceError: If the launch does not cite its source.
            MissingLaunchReasonError: If the product has neither a launch nor a reason.
        """
        if self.launched and not self.source:
            raise MissingLaunchSourceError(self.name)
        if not self.launched and not self.reason:
            raise MissingLaunchReasonError(self.name)
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def precision(self) -> Optional[LaunchPrecision]:
        """Get how precise the launch is.

        Returns:
            Optional[LaunchPrecision]: The precision, `None` without a launch.
        """
        if not self.launched:
            return None
        return (LaunchPrecision.YEAR, LaunchPrecision.MONTH, LaunchPrecision.DAY)[self.launched.count("-")]

    def launch_date(self) -> Optional[datetime]:
        """Get the launch as a date, the 1st of its month or year when only those are known.

        Returns:
            Optional[datetime]: The launch at midnight UTC, `None` without a launch.
        """
        if not self.launched:
            return None
        parts = [int(part) for part in self.launched.split("-")]
        return datetime(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1, tzinfo=UTC)
