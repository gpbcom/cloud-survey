from __future__ import annotations

# Standard Library Imports.
import json
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import TAXONOMY_PROMPTS_PATH
from llm.exception import LLMConfigurationFileError
from models.cloud.categorized_item import CategorizedItem
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.model.prompt_set import PromptSet
from models.taxonomy.labels.source_label import SourceLabel
from models.taxonomy.nodes.taxonomy import Taxonomy

type PromptValue = Union[str, int, List[str]]


class TaxonomyPrompt:
    """Write the prompts of the language model tasks: the stable system prompt, then the batch to answer.

    Attributes:
        DESCRIPTION_LIMIT (ClassVar[int]): The largest number of description characters sent per item.
        prompts (PromptSet): The task instructions.
        logger (Logger): The writer logger.

    Notes:
        The system prompt is the task instructions followed by the whole taxonomy (every visible slug with its
        English path and description): it is the same from one call to the next, so the provider caches it. The
        batch goes in the user message, as JSON.
    """

    DESCRIPTION_LIMIT: ClassVar[int] = 600

    def __init__(self, path: Path = TAXONOMY_PROMPTS_PATH, logger: Optional[Logger] = None) -> None:
        """Read the task instructions.

        Args:
            path (Path): The prompts file.
            logger (Optional[Logger]): The writer logger.

        Raises:
            LLMConfigurationFileError: If the prompts cannot be read.
        """
        self.logger = logger if logger else getLogger(__name__)
        try:
            self.prompts = PromptSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except (OSError, yaml.YAMLError, ValidationError) as e:
            self.logger.error("The taxonomy prompts %s cannot be read: %s", path, e)
            raise LLMConfigurationFileError(path, f"the prompts cannot be read ({e})") from e
        self.logger.debug("Taxonomy prompts read from %s.", path)

    ############################
    # Publicly Exposed Methods #
    ############################

    def system(self, task: LLMTask, taxonomy: Taxonomy) -> str:
        """Write the system prompt of a task.

        Args:
            task (LLMTask): The task.
            taxonomy (Taxonomy): The taxonomy the answers must name.

        Returns:
            str: The task instructions, then one line per visible node (`slug: Domain > Category: description`), the
                domains marked as such (`other` left out: the model never answers it).
        """
        instructions = (
            self.prompts.label_translation if task is LLMTask.LABEL_TRANSLATION else self.prompts.item_classification
        )
        lines: List[str] = []
        for domain in taxonomy.domains():
            if domain.hidden:
                continue
            lines.append(f"{domain.slug}: {domain.name_en} (domain): {domain.description_en}")
            for node in taxonomy.children(domain.slug):
                if not node.hidden:
                    lines.append(f"{node.slug}: {domain.name_en} > {node.name_en}: {node.description_en}")
        return f"{instructions}\n\nTaxonomy (slug: path: description):\n" + "\n".join(lines)

    def labels(self, labels: Sequence[SourceLabel], seen: Dict[int, List[str]]) -> str:
        """Write the batch of a label translation.

        Args:
            labels (Sequence[SourceLabel]): The labels.
            seen (Dict[int, List[str]]): The providers each label was seen at (context), by identifier.

        Returns:
            str: The labels, as a JSON list of `{id, text, providers}`.
        """
        batch: List[Dict[str, PromptValue]] = [
            {"id": label.id, "text": label.text, "providers": seen.get(label.id, [])} for label in labels
        ]
        return json.dumps({"labels": batch}, ensure_ascii=False)

    def items(self, items: Sequence[Tuple[int, str, CategorizedItem]]) -> str:
        """Write the batch of an item classification.

        Args:
            items (Sequence[Tuple[int, str, CategorizedItem]]): The identifier, provider and item of each item.

        Returns:
            str: The items, as a JSON list of `{id, provider, name, description, labels}`.
        """
        batch: List[Dict[str, PromptValue]] = []
        for item_id, provider, item in items:
            name, description = item.name_and_description()
            batch.append(
                {
                    "id": item_id,
                    "provider": provider,
                    "name": name,
                    "description": description[: self.DESCRIPTION_LIMIT],
                    "labels": item.raw_labels(),
                }
            )
        return json.dumps({"items": batch}, ensure_ascii=False)
