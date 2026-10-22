from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider, SoftwareAudience
from models.correspondence.enums import CardinalityClass, ConceptSource, CoverageFilter, MatchStrength, ViewMode
from models.correspondence.exception import InvalidColumnsError
from models.storage.pages.item_query import ItemQuery


class CorrespondenceQuery(BaseModel):
    """What the Correspondences tab shows: the provider columns and the filters of the concepts.

    Attributes:
        MIN_COLUMNS (ClassVar[int]): The smallest number of provider columns.
        MAX_COLUMNS (ClassVar[int]): The largest number of provider columns.
        columns (List[CloudProvider]): The provider columns, in their order.
        mode (ViewMode): Whether the rows are the concepts matched by the AI, or the taxonomy categories.
        service_categories (List[str]): Only the services filed under one of these taxonomy categories or domains.
        search (Optional[str]): Text contained in the concept name or in the name of one of its services.
        cardinalities (List[CardinalityClass]): Only the concepts of these classes over the columns (any when empty).
        coverage (CoverageFilter): Which concepts are shown, by the columns holding their services.
        strength (MatchStrength): Whether the partial services are shown.
        min_confidence (int): Only the services the language model filed with this confidence at least.
        sources (List[ConceptSource]): Only the services filed by these sources (any when empty).
        audiences (List[SoftwareAudience]): Only the services meant for one of these audiences.
        include_deleted (bool): Whether the services deleted from their catalogue are shown too.
        limit (int): The largest number of concepts read.

    Notes:
        A concept is shown when one service of a column at least passes the service filters: its other services are
        then filtered the same way.
    """

    model_config = ConfigDict(frozen=True)

    MIN_COLUMNS: ClassVar[int] = 2
    MAX_COLUMNS: ClassVar[int] = 40

    columns: List[CloudProvider] = Field(description="The provider columns, in their order.")
    mode: ViewMode = Field(default=ViewMode.CONCEPTS, description="What the rows stand for.")
    service_categories: List[str] = Field(default_factory=list, description="Only these taxonomy nodes.")
    search: Optional[str] = Field(default=None, max_length=200, description="Text in a concept or service name.")
    cardinalities: List[CardinalityClass] = Field(default_factory=list, description="Only these classes.")
    coverage: CoverageFilter = Field(default=CoverageFilter.ALL, description="Which concepts are shown.")
    strength: MatchStrength = Field(default=MatchStrength.ANY, description="Whether the partial services are shown.")
    min_confidence: int = Field(default=0, ge=0, le=100, description="The smallest confidence shown.")
    sources: List[ConceptSource] = Field(default_factory=list, description="Only the services of these sources.")
    audiences: List[SoftwareAudience] = Field(default_factory=list, description="Only these audiences.")
    include_deleted: bool = Field(default=False, description="Whether the deleted services are shown.")
    limit: int = Field(default=1000, ge=1, le=5000, description="The largest number of concepts read.")

    @field_validator("columns", mode="before")
    def validate_columns(cls, value: JsonValue) -> JsonValue:
        """Validate the raw columns: each provider once, 2 to 40 of them (every provider at once).

        Args:
            value (JsonValue): The raw providers.

        Returns:
            JsonValue: The providers, each once, in their order (their values are checked by pydantic afterwards).

        Raises:
            InvalidColumnsError: If there are fewer than 2 or more than 40 distinct providers.
        """
        if not isinstance(value, list):
            return value
        columns: List[JsonValue] = [*dict.fromkeys(str(provider) for provider in value)]
        if not cls.MIN_COLUMNS <= len(columns) <= cls.MAX_COLUMNS:
            raise InvalidColumnsError([str(column) for column in columns], cls.MIN_COLUMNS, cls.MAX_COLUMNS)
        return columns

    @field_validator("service_categories", mode="before")
    def validate_categories(cls, value: JsonValue) -> JsonValue:
        """Validate the raw taxonomy slugs: trimmed, each once.

        Args:
            value (JsonValue): The raw slugs.

        Returns:
            JsonValue: The cleaned slugs (checked by pydantic afterwards).
        """
        if isinstance(value, list):
            cleaned: List[JsonValue] = [*dict.fromkeys(str(slug).strip() for slug in value if str(slug).strip())]
            return cleaned
        return value

    @field_validator("search", mode="before")
    def validate_search(cls, value: JsonValue) -> JsonValue:
        """Validate the raw search text: trimmed, `None` when blank.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The trimmed text, `None` when missing or blank.
        """
        if isinstance(value, str):
            return value.strip() or None
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def item_query(self) -> ItemQuery:
        """Get the filters of the services, as a query of the catalogue products.

        Returns:
            ItemQuery: The products of the columns, of the categories, audiences and deletion state of the query.
        """
        return ItemQuery(
            providers=list(self.columns),
            restrict_providers=True,
            service_categories=list(self.service_categories),
            audiences=list(self.audiences),
            include_deleted=self.include_deleted,
        )
