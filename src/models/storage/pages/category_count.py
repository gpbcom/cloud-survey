from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class CategoryCount(BaseModel):
    """The number of stored software under a category of a marketplace taxonomy.

    Attributes:
        SEPARATOR (ClassVar[str]): The separator of the levels in a readable label.
        path (List[str]): The category labels, from the root of the taxonomy to the category.
        count (int): The number of software under the category.
    """

    model_config = ConfigDict(frozen=True)

    SEPARATOR: ClassVar[str] = " > "

    path: List[str] = Field(min_length=1, max_length=6, description="The category labels, from the root.")
    count: int = Field(ge=0, description="The number of software under the category.")

    def label(self) -> str:
        """Get a readable label of the category, with the categories above it.

        Returns:
            str: The labels of the path, from the root, e.g. `AI Agents & Tools > Content Creation`.
        """
        return self.SEPARATOR.join(self.path)
