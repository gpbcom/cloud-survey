from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class StoredResearcher(BaseModel):
    """A stored researcher profile of a company.

    Attributes:
        author_id (str): The OpenAlex author.
        company (str): The company they wrote for.
        name (str): Their name.
        orcid (Optional[str]): Their ORCID.
        works_count (int): The works OpenAlex counts for them.
        cited_by_count (int): The citations their works received.
        h_index (Optional[int]): Their h-index.
        institution (Optional[str]): Where they were last seen.
    """

    model_config = ConfigDict(frozen=True)

    author_id: str = Field(min_length=1, description="The OpenAlex author.")
    company: str = Field(min_length=1, description="The company they wrote for.")
    name: str = Field(min_length=1, description="Their name.")
    orcid: Optional[str] = Field(default=None, description="Their ORCID.")
    works_count: int = Field(default=0, ge=0, description="Their works.")
    cited_by_count: int = Field(default=0, ge=0, description="The citations of their works.")
    h_index: Optional[int] = Field(default=None, ge=0, description="Their h-index.")
    institution: Optional[str] = Field(default=None, description="Where they were last seen.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def link(self) -> str:
        """Get the page to open for the researcher.

        Returns:
            str: Their OpenAlex page.
        """
        return f"https://openalex.org/{self.author_id}"
