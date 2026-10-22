from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import SoftwareCategory
from models.taxonomy.enums import NodeOrigin
from models.taxonomy.exception import InvalidSlugError


class TaxonomyNode(BaseModel):
    """A node of the unified taxonomy: a domain (no parent) or a category of a domain.

    Attributes:
        SLUG_PATTERN (ClassVar[str]): The pattern of the slugs: kebab-case words.
        slug (str): The identifier of the node, never changed (the items and the rules name it).
        parent_slug (Optional[str]): The domain of a category, `None` for a domain.
        name_en (str): The English name.
        name_ru (str): The Russian name.
        name_zh (str): The Chinese name.
        description_en (str): What the node holds, in one English line.
        position (int): The order of the node among its siblings.
        audiences (List[SoftwareCategory]): Who its items are meant for (inherited from the domain when empty).
        origin (NodeOrigin): Whether the node comes from the seed file or from a person.
        edited (bool): Whether a person edited the node (the seed then leaves it unchanged).
        hidden (bool): Whether the node is hidden from the pickers.
        umbrella (bool): Whether the category is the generic one of its domain, dropped next to a more specific one.
    """

    model_config = ConfigDict(frozen=True)

    SLUG_PATTERN: ClassVar[str] = r"^[a-z0-9]+(-[a-z0-9]+)*$"

    slug: str = Field(min_length=1, max_length=60, description="The identifier of the node.")
    parent_slug: Optional[str] = Field(default=None, max_length=60, description="The domain of a category.")
    name_en: str = Field(min_length=1, description="The English name.")
    name_ru: str = Field(min_length=1, description="The Russian name.")
    name_zh: str = Field(min_length=1, description="The Chinese name.")
    description_en: str = Field(default="", description="What the node holds, in one English line.")
    position: int = Field(default=0, ge=0, description="The order of the node among its siblings.")
    audiences: List[SoftwareCategory] = Field(default_factory=list, description="Who its items are meant for.")
    origin: NodeOrigin = Field(default=NodeOrigin.SEED, description="Where the node comes from.")
    edited: bool = Field(default=False, description="Whether a person edited the node.")
    hidden: bool = Field(default=False, description="Whether the node is hidden from the pickers.")
    umbrella: bool = Field(default=False, description="Whether the category is the generic one of its domain.")

    @field_validator("slug", "parent_slug", mode="before")
    def validate_slug(cls, value: JsonValue) -> JsonValue:
        """Validate a raw slug: kebab-case words.

        Args:
            value (JsonValue): The raw slug.

        Returns:
            JsonValue: The unchanged slug (its type is checked by pydantic afterwards).

        Raises:
            InvalidSlugError: If the slug is not kebab-case.
        """
        if isinstance(value, str) and not re.fullmatch(cls.SLUG_PATTERN, value):
            raise InvalidSlugError(value)
        return value

    @field_validator("audiences", mode="before")
    def validate_audiences(cls, value: JsonValue) -> JsonValue:
        """Validate the raw audiences: duplicates dropped, a missing list read as empty.

        Args:
            value (JsonValue): The raw audiences.

        Returns:
            JsonValue: The audiences without duplicates (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(item for item in value if isinstance(item, str)))
        return value

    def is_domain(self) -> bool:
        """Tell whether the node is a domain.

        Returns:
            bool: Whether the node has no parent.
        """
        return self.parent_slug is None
