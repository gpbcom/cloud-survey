from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.config.compounding_settings import CompoundingSettings
from models.compounding.config.foundations.category_foundations import CategoryFoundations
from models.compounding.config.market_size_point import MarketSizePoint
from models.compounding.config.scope.excluded_provider import ExcludedProvider
from models.compounding.config.scope.provider_scope import ProviderScope
from models.compounding.exception import DuplicateCompoundingEntryError, InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class CompoundingConfig(BaseModel):
    """The scope and the curated inputs of the service-compounding analysis.

    Attributes:
        SLUG (ClassVar[Pattern[str]]): The format of a taxonomy slug.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        providers (List[ProviderScope]): The public-cloud providers analysed, each once.
        excluded (List[ExcludedProvider]): The providers fitted apart, each with its reason.
        domains (List[str]): The taxonomy domains of the cloud computing market kept.
        market (List[MarketSizePoint]): The curated market sizes, each year once.
        foundations (List[CategoryFoundations]): The foundation set of each dependent category, each once.
        settings (CompoundingSettings): How the models are fitted.

    Notes:
        The file is `conf/analysis/compounding.yaml`. The slugs are checked against the taxonomy by the loader.
    """

    SLUG: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    providers: List[ProviderScope] = Field(min_length=1, description="The providers analysed.")
    excluded: List[ExcludedProvider] = Field(default_factory=list, description="The providers fitted apart.")
    domains: List[str] = Field(min_length=1, description="The domains kept.")
    market: List[MarketSizePoint] = Field(default_factory=list, description="The curated market sizes.")
    foundations: List[CategoryFoundations] = Field(default_factory=list, description="The foundation sets.")
    settings: CompoundingSettings = Field(default_factory=CompoundingSettings, description="How models are fitted.")

    @field_validator("providers", "excluded", mode="before")
    def validate_providers(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw providers: a list, each provider once.

        Args:
            value (JsonValue): The raw providers.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The providers (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a provider is listed twice.
        """
        items = cls.CHECK.items(value, f"{info.field_name} providers", "mappings with a provider")
        seen: List[str] = []
        for item in items:
            name = item.get("provider") if isinstance(item, dict) else None
            if name is not None:
                if str(name) in seen:
                    raise DuplicateCompoundingEntryError("provider", str(name))
                seen.append(str(name))
        return items

    @field_validator("domains", mode="before")
    def validate_domains(cls, value: JsonValue) -> JsonValue:
        """Validate the raw domains: kebab-case slugs, each once.

        Args:
            value (JsonValue): The raw domains.

        Returns:
            JsonValue: The domains.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidCompoundingValueError: If a domain is not a kebab-case slug.
            DuplicateCompoundingEntryError: If a domain is listed twice.
        """
        domains: List[JsonValue] = []
        for item in cls.CHECK.items(value, "domains", "taxonomy domain slugs"):
            slug = cls.CHECK.text(item, "domain", 60) or ""
            if not cls.SLUG.match(slug):
                raise InvalidCompoundingValueError("domain", slug, "a kebab-case slug")
            if slug in domains:
                raise DuplicateCompoundingEntryError("domain", slug)
            domains.append(slug)
        return domains

    @field_validator("market", mode="before")
    def validate_market(cls, value: JsonValue) -> JsonValue:
        """Validate the raw market sizes: a list, each year once.

        Args:
            value (JsonValue): The raw sizes.

        Returns:
            JsonValue: The sizes (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a year is listed twice.
        """
        items = cls.CHECK.items(value, "market sizes", "mappings with a year, a size and a source")
        seen: List[str] = []
        for item in items:
            name = item.get("year") if isinstance(item, dict) else None
            if name is not None:
                if str(name) in seen:
                    raise DuplicateCompoundingEntryError("market year", str(name))
                seen.append(str(name))
        return items

    @field_validator("foundations", mode="before")
    def validate_foundations(cls, value: JsonValue) -> JsonValue:
        """Validate the raw foundation sets: a list, each category once, never its own foundation.

        Args:
            value (JsonValue): The raw foundation sets.

        Returns:
            JsonValue: The sets (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a category is listed twice.
            InvalidCompoundingValueError: If a category is its own foundation.
        """
        items = cls.CHECK.items(value, "foundation sets", "mappings with a category and links")
        seen: List[str] = []
        for item in items:
            name = item.get("category") if isinstance(item, dict) else None
            if name is not None:
                if str(name) in seen:
                    raise DuplicateCompoundingEntryError("dependent category", str(name))
                seen.append(str(name))
        for item in items:
            if not isinstance(item, dict):
                continue
            links = item.get("links")
            if isinstance(links, list) and any(
                isinstance(link, dict) and link.get("foundation") == item.get("category") for link in links
            ):
                raise InvalidCompoundingValueError("foundation set", str(item.get("category")), "no self-link")
        return items

    @field_validator("settings", mode="before")
    def validate_settings(cls, value: JsonValue) -> JsonValue:
        """Validate the raw settings: a mapping, none meaning the defaults.

        Args:
            value (JsonValue): The raw settings.

        Returns:
            JsonValue: The settings (validated by their model afterwards).

        Raises:
            InvalidCompoundingValueError: If they are neither missing nor a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, (dict, CompoundingSettings)):
            raise InvalidCompoundingValueError("settings", repr(value), "a mapping")
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def kept(self) -> List[CloudProvider]:
        """Get the providers analysed.

        Returns:
            List[CloudProvider]: The providers, in their order.
        """
        return [scope.provider for scope in self.providers]

    def start(self, provider: CloudProvider) -> Optional[int]:
        """Get the first year of a provider's public cloud.

        Args:
            provider (CloudProvider): The provider.

        Returns:
            Optional[int]: The year, `None` when not configured.
        """
        return next((scope.start for scope in self.providers if scope.provider is provider), None)

    def foundation_sets(self) -> Dict[str, List[str]]:
        """Get the curated foundations of each dependent category.

        Returns:
            Dict[str, List[str]]: The foundations of each dependent category.
        """
        return {entry.category: entry.foundations() for entry in self.foundations}

    def market_sizes(self) -> Dict[int, float]:
        """Get the curated market sizes.

        Returns:
            Dict[int, float]: The size of each year, in billion USD.
        """
        return {point.year: point.size_bn for point in self.market}
