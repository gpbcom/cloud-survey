from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Iterable, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr, field_validator

# First Party Imports.
from models.cloud.enums import SoftwareCategory
from models.taxonomy.exception import InvalidTaxonomyTreeError
from models.taxonomy.nodes.taxonomy_node import TaxonomyNode


class Taxonomy(BaseModel):
    """The unified taxonomy: domains holding categories, two levels.

    Attributes:
        nodes (List[TaxonomyNode]): The domains and categories, in display order (domains by position, each followed
            by its categories).

    Notes:
        - The lookups (node by slug, order, parents) are indexed once, when the taxonomy is built: the classifier asks
          them for every item.
        - A category without audiences of its own has those of its domain.
    """

    model_config = ConfigDict(frozen=True)

    nodes: List[TaxonomyNode] = Field(default_factory=list, description="The domains and categories, in order.")

    _by_slug: Dict[str, TaxonomyNode] = PrivateAttr(default_factory=dict)
    _order: Dict[str, int] = PrivateAttr(default_factory=dict)

    @field_validator("nodes", mode="before")
    def validate_nodes(cls, value: JsonValue) -> JsonValue:
        """Validate the raw tree: unique slugs, every category under an existing domain, two levels only.

        Args:
            value (JsonValue): The raw nodes.

        Returns:
            JsonValue: The unchanged nodes (their content is checked by pydantic afterwards).

        Raises:
            InvalidTaxonomyTreeError: If a slug is repeated, a parent is unknown or is itself a category.
        """
        if not isinstance(value, list):
            return value
        raw = [item.model_dump() if isinstance(item, TaxonomyNode) else item for item in value]
        rows = [item for item in raw if isinstance(item, dict)]
        slugs = [str(row.get("slug")) for row in rows]
        parents = {str(row.get("slug")): row.get("parent_slug") for row in rows}
        problems = sorted({f"the slug {slug!r} is repeated" for slug in slugs if slugs.count(slug) > 1})
        for slug, parent in parents.items():
            if parent is None:
                continue
            if parent not in parents:
                problems.append(f"the category {slug!r} is under the unknown domain {parent!r}")
            elif parents[parent] is not None:
                problems.append(f"the category {slug!r} is under the category {parent!r}, not a domain")
        if problems:
            raise InvalidTaxonomyTreeError(problems)
        return value

    ############################
    # Internal Helpers Methods #
    ############################

    def _index(self) -> Dict[str, TaxonomyNode]:
        """Index the nodes by slug, once.

        Returns:
            Dict[str, TaxonomyNode]: The node of each slug.
        """
        if len(self._by_slug) != len(self.nodes):
            self._by_slug = {node.slug: node for node in self.nodes}
            self._order = {node.slug: index for index, node in enumerate(self.nodes)}
        return self._by_slug

    ############################
    # Publicly Exposed Methods #
    ############################

    def node(self, slug: str) -> Optional[TaxonomyNode]:
        """Get a node.

        Args:
            slug (str): Its slug.

        Returns:
            Optional[TaxonomyNode]: The node, `None` when unknown.
        """
        return self._index().get(slug)

    def is_domain(self, slug: str) -> bool:
        """Tell whether a slug names a domain.

        Args:
            slug (str): The slug.

        Returns:
            bool: Whether it is a known domain.
        """
        node = self._index().get(slug)
        return node is not None and node.is_domain()

    def is_category(self, slug: str) -> bool:
        """Tell whether a slug names a category.

        Args:
            slug (str): The slug.

        Returns:
            bool: Whether it is a known category.
        """
        node = self._index().get(slug)
        return node is not None and not node.is_domain()

    def domains(self) -> List[TaxonomyNode]:
        """Get the domains.

        Returns:
            List[TaxonomyNode]: The domains, in display order.
        """
        return [node for node in self.nodes if node.is_domain()]

    def children(self, domain: str) -> List[TaxonomyNode]:
        """Get the categories of a domain.

        Args:
            domain (str): The domain slug.

        Returns:
            List[TaxonomyNode]: Its categories, in display order.
        """
        return [node for node in self.nodes if node.parent_slug == domain]

    def domain_of(self, slug: str) -> Optional[str]:
        """Get the domain of a node: the domain itself, or the parent of a category.

        Args:
            slug (str): The slug.

        Returns:
            Optional[str]: The domain slug, `None` for an unknown slug.
        """
        node = self._index().get(slug)
        if node is None:
            return None
        return node.slug if node.parent_slug is None else node.parent_slug

    def audiences_of(self, slug: str) -> List[SoftwareCategory]:
        """Get who the items of a node are meant for.

        Args:
            slug (str): The slug.

        Returns:
            List[SoftwareCategory]: The audiences of the node, else of its domain, empty for an unknown slug.
        """
        node = self._index().get(slug)
        if node is None:
            return []
        if node.audiences or node.parent_slug is None:
            return list(node.audiences)
        parent = self._index().get(node.parent_slug)
        return list(parent.audiences) if parent is not None else []

    def umbrella_of(self, domain: str) -> Optional[str]:
        """Get the generic category of a domain.

        Args:
            domain (str): The domain slug.

        Returns:
            Optional[str]: The slug of its umbrella category, `None` when it has none.
        """
        return next((node.slug for node in self.children(domain) if node.umbrella), None)

    def ordered(self, slugs: Iterable[str]) -> List[str]:
        """Sort slugs in the display order, unknown slugs dropped, each once.

        Args:
            slugs (Iterable[str]): The slugs.

        Returns:
            List[str]: The known slugs, in display order.
        """
        self._index()
        known = {slug for slug in slugs if slug in self._order}
        return sorted(known, key=lambda slug: self._order[slug])
