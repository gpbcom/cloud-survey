from __future__ import annotations

# Standard Library Imports.
import json
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

# First Party Imports.
from conf import TAXONOMY_PROMPTS_PATH
from llm.tasks.taxonomy_prompt import TaxonomyPrompt
from models.correspondence.rows.bucket_service import BucketService
from models.correspondence.rows.concept_row import ConceptRow
from models.taxonomy.nodes.taxonomy import Taxonomy

type PromptValue = Optional[Union[str, int, List[str], List[Dict[str, Union[str, int]]]]]


class CorrespondencePrompt:
    """Write the prompts of the service correspondences: the stable instructions, then one category of services.

    Attributes:
        instructions (str): The system prompt of the task (`service_correspondence` of `conf/taxonomy/prompts.yaml`).
        logger (Logger): The writer logger.

    Notes:
        The system prompt holds the instructions only, the same for every call (cached by the provider): the
        category, its concepts and its services go in the user message, as JSON.
    """

    def __init__(self, path: Path = TAXONOMY_PROMPTS_PATH, logger: Optional[Logger] = None) -> None:
        """Read the instructions.

        Args:
            path (Path): The prompts file.
            logger (Optional[Logger]): The writer logger.

        Raises:
            LLMConfigurationFileError: If the prompts cannot be read.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.instructions = TaxonomyPrompt(path, self.logger).prompts.service_correspondence
        self.logger.debug("Service correspondence prompt read from %s.", path)

    ############################
    # Internal Helpers Methods #
    ############################

    def _path(self, taxonomy: Taxonomy, slug: str) -> str:
        """Write the English path of a taxonomy node.

        Args:
            taxonomy (Taxonomy): The taxonomy.
            slug (str): The node.

        Returns:
            str: `Domain > Category` for a category, the domain name for a domain, the slug when unknown.
        """
        node = taxonomy.node(slug)
        if node is None:
            return slug
        domain = taxonomy.node(node.parent_slug) if node.parent_slug else None
        return f"{domain.name_en} > {node.name_en}" if domain is not None else node.name_en

    ############################
    # Publicly Exposed Methods #
    ############################

    def system(self) -> str:
        """Get the system prompt.

        Returns:
            str: The instructions of the task.
        """
        return self.instructions

    def batch(
        self, taxonomy: Taxonomy, slug: str, concepts: Sequence[ConceptRow], services: Sequence[BucketService]
    ) -> str:
        """Write the user message of a call: the category, its concepts and the services to match.

        Args:
            taxonomy (Taxonomy): The taxonomy, naming the category.
            slug (str): The category.
            concepts (Sequence[ConceptRow]): The concepts already found in the category.
            services (Sequence[BucketService]): The services to match.

        Returns:
            str: The JSON message `{category, concepts: [{concept_id, name, description, services}], services}`.
        """
        message: Dict[str, PromptValue] = {"category": self._path(taxonomy, slug)}
        known: List[Dict[str, PromptValue]] = []
        for concept in concepts:
            members: List[Dict[str, Union[str, int]]] = [
                {"id": member.product_id, "provider": member.provider.value, "name": member.name}
                for member in concept.members
            ]
            known.append(
                {
                    "concept_id": concept.id,
                    "name": concept.name,
                    "description": concept.description,
                    "services": members,
                }
            )
        sent: List[Dict[str, PromptValue]] = [
            {
                "id": service.product_id,
                "provider": service.provider.value,
                "name": service.name,
                "description": service.description,
                "labels": list(service.labels),
            }
            for service in services
        ]
        return json.dumps({**message, "concepts": known, "services": sent}, ensure_ascii=False)
