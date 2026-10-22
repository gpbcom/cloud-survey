from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Type, TypeVar

# Third Party Imports.
import yaml
from pydantic import BaseModel, ValidationError

# First Party Imports.
from conf import LABEL_SEED_PATH, TAXONOMY_SEED_PATH
from models.classification.classification_rules import ClassificationRules
from models.taxonomy.nodes.taxonomy import Taxonomy
from models.taxonomy.seed.label_seed import LabelSeed
from models.taxonomy.seed.taxonomy_seed import TaxonomySeed
from taxonomy.exception import TaxonomySeedFileError, UnknownTaxonomySlugError

SeedModel = TypeVar("SeedModel", bound=BaseModel)


class TaxonomySeedLoader:
    """Load the taxonomy seed files, and check that the rules and seeds only name existing taxonomy nodes.

    Attributes:
        logger (Logger): The loader logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _read(self, path: Path, model: Type[SeedModel]) -> SeedModel:
        """Read and validate a YAML seed file.

        Args:
            path (Path): The file.
            model (Type[SeedModel]): The model of its content.

        Returns:
            SeedModel: The validated content.

        Raises:
            TaxonomySeedFileError: If the file cannot be read, is not valid YAML or holds invalid content.
        """
        self.logger.debug("Loading the taxonomy seed %s.", path)
        try:
            with path.open(encoding="utf-8") as file:
                return model.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The taxonomy seed %s cannot be read: %s", path, e.strerror)
            raise TaxonomySeedFileError(path, f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The taxonomy seed %s is not valid YAML.", path)
            raise TaxonomySeedFileError(path, f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The taxonomy seed %s is invalid (%d errors).", path, e.error_count())
            raise TaxonomySeedFileError(path, f"the content is invalid.\n{e}") from e

    def _unknown(self, taxonomy: Taxonomy, named: Iterable[Tuple[str, str]]) -> List[str]:  # noqa: E501
        """List the slugs named somewhere which are not taxonomy nodes.

        Args:
            taxonomy (Taxonomy): The taxonomy.
            named (Iterable[Tuple[str, str]]): Where each slug is named, and the slug.

        Returns:
            List[str]: One problem per unknown slug, sorted.
        """
        return sorted({f"{where} names the unknown node {slug!r}" for where, slug in named if not taxonomy.node(slug)})  # noqa: E501

    ############################
    # Publicly Exposed Methods #
    ############################

    def load_taxonomy(self, path: Path = TAXONOMY_SEED_PATH) -> Taxonomy:
        """Load the taxonomy seed file.

        Args:
            path (Path): The taxonomy seed file.

        Returns:
            Taxonomy: Its domains and categories.

        Raises:
            TaxonomySeedFileError: If the file cannot be loaded, or its nodes do not form a valid tree.
        """
        seed = self._read(path, TaxonomySeed)
        try:
            taxonomy = seed.to_taxonomy()
        except ValidationError as e:
            self.logger.error("The taxonomy seed %s is not a valid tree (%d errors).", path, e.error_count())
            raise TaxonomySeedFileError(path, f"the nodes do not form a valid tree.\n{e}") from e
        self.logger.debug("Taxonomy seed loaded: %d domains, %d nodes.", len(taxonomy.domains()), len(taxonomy.nodes))  # noqa: E501
        return taxonomy

    def load_labels(self, path: Path = LABEL_SEED_PATH) -> LabelSeed:
        """Load the label seed file.

        Args:
            path (Path): The label seed file.

        Returns:
            LabelSeed: The seeded labels, empty when the file does not exist.

        Raises:
            TaxonomySeedFileError: If the file exists but cannot be loaded.
        """
        if not path.exists():
            self.logger.warning("No label seed %s: the labels will only be translated by the model or by hand.", path)
            return LabelSeed()
        labels = self._read(path, LabelSeed)
        self.logger.debug("Label seed loaded: %d labels.", len(labels.labels))
        return labels

    def check(self, taxonomy: Taxonomy, rules: ClassificationRules, labels: Optional[LabelSeed] = None) -> None:  # noqa: E501
        """Check that the rules and the label seed only name taxonomy nodes, and that every former type is a category.

        Args:
            taxonomy (Taxonomy): The taxonomy.
            rules (ClassificationRules): The classification rules.
            labels (Optional[LabelSeed]): The label seed, if checked too.

        Raises:
            UnknownTaxonomySlugError: If a rule, a delivery fallback or a seeded label names an unknown node, or a
                former software type is not a category.
        """
        named: List[Tuple[str, str]] = []
        for section, section_rules in (
            ("name_rules", rules.name_rules),
            ("category_rules", rules.category_rules),
            ("keyword_rules", rules.keyword_rules),
        ):
            named += [(f"{section} {rule.pattern!r}", slug) for rule in section_rules for slug in rule.categories]  # noqa: E501
        named += [
            (f"delivery_categories {delivery.value!r}", slug)
            for delivery, slugs in rules.delivery_categories.items()
            for slug in slugs
        ]
        if labels is not None:
            named += [(f"label seed {label.text!r}", slug) for label in labels.labels for slug in label.links]  # noqa: E501
        problems = self._unknown(taxonomy, named)
        if problems:
            self.logger.error("The taxonomy does not match its rules and seeds: %d problems.", len(problems))
            raise UnknownTaxonomySlugError(problems)
        self.logger.debug("Rules and seeds name %d taxonomy nodes, all known.", len({slug for _, slug in named}))
