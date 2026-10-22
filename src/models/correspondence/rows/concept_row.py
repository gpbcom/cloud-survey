from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.correspondence.enums import CardinalityClass, ConceptSource, MatchStrength, MemberRole
from models.correspondence.exception import EmptyConceptNameError
from models.correspondence.rows.concept_member import ConceptMember


class ConceptRow(BaseModel):
    """A service concept (e.g. "Managed Kubernetes") with the services of every provider filed under it.

    Attributes:
        CLASSES (ClassVar[Dict[int, CardinalityClass]]): The class of the largest number of services of one side.
        id (int): The storage identifier of the concept.
        name (str): Its English name.
        description (str): What it stands for, in one line.
        node_slug (Optional[str]): The taxonomy category it was found in.
        source (ConceptSource): Who created it.
        edited (bool): Whether a person changed it.
        members (List[ConceptMember]): Its services, every provider included.

    Notes:
        The correspondences of two providers are the services they both file under a concept: a provider with two
        services of the concept and another with one make a 2:1 correspondence.
    """

    model_config = ConfigDict(frozen=True)

    CLASSES: ClassVar[Dict[int, CardinalityClass]] = {
        1: CardinalityClass.ONE_TO_ONE,
        2: CardinalityClass.TWO_TO_ONE,
        3: CardinalityClass.THREE_TO_ONE,
    }

    id: int = Field(ge=1, description="The storage identifier of the concept.")
    name: str = Field(min_length=1, description="Its English name.")
    description: str = Field(default="", description="What it stands for.")
    node_slug: Optional[str] = Field(default=None, description="The taxonomy category it was found in.")
    source: ConceptSource = Field(default=ConceptSource.LLM, description="Who created it.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
    members: List[ConceptMember] = Field(default_factory=list, description="Its services.")

    @field_validator("name", mode="before")
    def validate_name(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The cleaned name (its type is checked by pydantic afterwards).

        Raises:
            EmptyConceptNameError: If the name is missing or blank.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            raise EmptyConceptNameError()
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    def validate_description(cls, value: JsonValue) -> JsonValue:
        """Validate the raw description: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw description.

        Returns:
            JsonValue: The cleaned description, empty when missing.
        """
        if value is None:
            return ""
        return " ".join(value.split()) if isinstance(value, str) else value

    ############################
    # Publicly Exposed Methods #
    ############################

    def members_of(self, provider: CloudProvider, strength: MatchStrength = MatchStrength.ANY) -> List[ConceptMember]:
        """Get the services of a provider filed under the concept.

        Args:
            provider (CloudProvider): The provider.
            strength (MatchStrength): Whether the partial services are kept.

        Returns:
            List[ConceptMember]: Its services, the equivalent ones first, then by name.
        """
        kept = [
            member
            for member in self.members
            if member.provider is provider and (strength is MatchStrength.ANY or member.role is MemberRole.EQUIVALENT)
        ]
        return sorted(kept, key=lambda member: (member.role is not MemberRole.EQUIVALENT, member.name.casefold()))

    def covered(self, columns: Sequence[CloudProvider], strength: MatchStrength = MatchStrength.ANY) -> int:
        """Count the columns holding a service of the concept.

        Args:
            columns (Sequence[CloudProvider]): The provider columns.
            strength (MatchStrength): Whether the partial services count.

        Returns:
            int: The number of columns with one service at least.
        """
        return sum(bool(self.members_of(provider, strength)) for provider in columns)

    def cardinality(
        self, left: CloudProvider, right: CloudProvider, strength: MatchStrength = MatchStrength.ANY
    ) -> CardinalityClass:
        """Classify the correspondence of two providers in the concept.

        Args:
            left (CloudProvider): The first provider.
            right (CloudProvider): The second provider.
            strength (MatchStrength): Whether the partial services count.

        Returns:
            CardinalityClass: `missing` when one of them has no service, else the class of the larger side.
        """
        counts = (len(self.members_of(left, strength)), len(self.members_of(right, strength)))
        if min(counts) == 0:
            return CardinalityClass.MISSING
        return self.CLASSES.get(max(counts), CardinalityClass.MANY_TO_ONE)

    def row_class(
        self, columns: Sequence[CloudProvider], strength: MatchStrength = MatchStrength.ANY
    ) -> CardinalityClass:
        """Classify the concept over the provider columns.

        Args:
            columns (Sequence[CloudProvider]): The provider columns.
            strength (MatchStrength): Whether the partial services count.

        Returns:
            CardinalityClass: `missing` when fewer than two columns hold a service, else the class of the column
                holding the most services.
        """
        counts = [count for provider in columns if (count := len(self.members_of(provider, strength)))]
        if len(counts) < 2:
            return CardinalityClass.MISSING
        return self.CLASSES.get(max(counts), CardinalityClass.MANY_TO_ONE)
