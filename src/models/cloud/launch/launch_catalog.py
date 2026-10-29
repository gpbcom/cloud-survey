from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

# First Party Imports.
from models.cloud.exception import DuplicateLaunchEntryError, InvalidLaunchFieldError
from models.cloud.launch.curated_launch import CuratedLaunch
from models.cloud.launch.launch_alias import LaunchAlias


class LaunchCatalog(BaseModel):
    """The launch dates catalogue (`data/curated/launches.json`): what completes the dated sources of the crawlers.

    Attributes:
        aliases (List[LaunchAlias]): The names the dated sources give the products renamed since.
        launches (List[CuratedLaunch]): The launches read by hand, and the products known to have no source.

    Notes:
        The catalogue only completes the crawlers: a curated launch wins over the date a crawler reads, for the
        products whose dated source is missing, starts after their launch or names them otherwise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    aliases: List[LaunchAlias] = Field(default_factory=list, description="The former names of the products.")
    launches: List[CuratedLaunch] = Field(default_factory=list, description="The launches read by hand.")

    @field_validator("aliases", "launches", mode="before")
    def validate_entries(cls, value: JsonValue) -> JsonValue:
        """Validate a raw list of entries: a list, empty when missing.

        Args:
            value (JsonValue): The raw entries.

        Returns:
            JsonValue: The entries.

        Raises:
            InvalidLaunchFieldError: If it is not a list.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise InvalidLaunchFieldError("entries", str(value), "a list")
        return value

    @model_validator(mode="after")
    def validate_unique(self) -> LaunchCatalog:
        """Check that each product is listed once per crawler, among the aliases and among the launches.

        Returns:
            LaunchCatalog: The catalogue.

        Raises:
            DuplicateLaunchEntryError: If a product is listed twice.
        """
        for entries in (self.aliases, self.launches):
            self._check_unique([(entry.crawler, entry.name) for entry in entries])
        return self

    ############################
    # Internal Helpers Methods #
    ############################

    def _check_unique(self, keys: Sequence[Tuple[str, str]]) -> None:
        """Check that no product is listed twice for a crawler (names compared case-insensitively).

        Args:
            keys (Sequence[Tuple[str, str]]): The crawler and the product of each entry.

        Raises:
            DuplicateLaunchEntryError: If a product is listed twice.
        """
        seen: Set[Tuple[str, str]] = set()
        for crawler, name in keys:
            key = (crawler, name.casefold())
            if key in seen:
                raise DuplicateLaunchEntryError(crawler, name)
            seen.add(key)

    ############################
    # Publicly Exposed Methods #
    ############################

    def aliases_of(self, crawler: str) -> Dict[str, str]:
        """Get the names the dated source of a crawler gives its products.

        Args:
            crawler (str): The crawler name, e.g. `azure`.

        Returns:
            Dict[str, str]: The dated source's name of each catalogue product name.
        """
        return {alias.name: alias.feed_name for alias in self.aliases if alias.crawler == crawler}

    def launches_of(self, crawler: str) -> List[CuratedLaunch]:
        """Get the curated launches of a crawler's products.

        Args:
            crawler (str): The crawler name, e.g. `gcp`.

        Returns:
            List[CuratedLaunch]: Its curated launches, known gaps included.
        """
        return [launch for launch in self.launches if launch.crawler == crawler]
