from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.taxonomy.nodes.taxonomy import Taxonomy
from models.taxonomy.nodes.taxonomy_node import TaxonomyNode
from models.taxonomy.seed.seed_domain import SeedDomain


class TaxonomySeed(BaseModel):
    """The taxonomy seed file of the project: its domains and their categories.

    Attributes:
        domains (List[SeedDomain]): The domains, in display order, at least one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    domains: List[SeedDomain] = Field(min_length=1, description="The domains, in display order.")

    def to_taxonomy(self) -> Taxonomy:
        """Build the taxonomy of the seed.

        Returns:
            Taxonomy: The domains and categories, positioned in the order of the file, the categories keeping their
                own audiences only (the taxonomy inherits the others from their domain).
        """
        nodes: List[TaxonomyNode] = []
        for domain_position, domain in enumerate(self.domains):
            nodes.append(
                TaxonomyNode(
                    slug=domain.slug,
                    name_en=domain.en,
                    name_ru=domain.ru,
                    name_zh=domain.zh,
                    description_en=domain.description,
                    position=domain_position,
                    audiences=domain.audiences,
                    hidden=domain.hidden,
                )
            )
            nodes += [
                TaxonomyNode(
                    slug=category.slug,
                    parent_slug=domain.slug,
                    name_en=category.en,
                    name_ru=category.ru,
                    name_zh=category.zh,
                    description_en=category.description,
                    position=position,
                    audiences=category.audiences,
                    hidden=category.hidden,
                    umbrella=category.umbrella,
                )
                for position, category in enumerate(domain.categories)
            ]
        return Taxonomy(nodes=nodes)
