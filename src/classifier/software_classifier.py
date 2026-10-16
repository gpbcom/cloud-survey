from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Iterable, List, Optional, Sequence, Tuple

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from classifier.exception import ClassificationRulesFileError
from conf import CLASSIFICATION_RULES_PATH
from models.classification.classification_rules import ClassificationRules
from models.cloud.enums import DeliveryMethod, SoftwareCategory, SoftwareType

CompiledTypeRule = Tuple[re.Pattern[str], List[SoftwareType]]
CompiledCategoryHint = Tuple[re.Pattern[str], List[SoftwareCategory]]


class SoftwareClassifier:
    """Classify the marketplace software into categories and types, with deterministic rules.

    Attributes:
        OVER_TICKED (ClassVar[int]): Above this number of types given by the marketplace categories, a listing is
            deemed over-ticked: only the types its keywords confirm are kept, when any.
        rules (ClassificationRules): The classification rules.
        name_rules (List[CompiledTypeRule]): The compiled well-known product rules.
        category_rules (List[CompiledTypeRule]): The compiled marketplace category rules.
        keyword_rules (List[CompiledTypeRule]): The compiled name and description rules.
        category_hints (List[CompiledCategoryHint]): The compiled category hints.
        packaging_suffix (Optional[re.Pattern[str]]): The compiled packaging suffix of the names, if any.

    Notes:
        The types of a software are, in this order of precedence: the types of a well-known product (name rules), the
        types of over-ticked marketplace categories confirmed by its keywords (name, else description), the types of its
        marketplace categories together with the keyword types of its name, the keyword types of its description, else
        `other`. The names are matched without their packaging suffix (e.g. ` on Ubuntu 24.04`). Its categories are
        those of its types, plus the ones hinted by the marketplace categories. A software of unknown type gets the
        category of its delivery method.
    """

    OVER_TICKED: ClassVar[int] = 2

    def __init__(
        self,
        rules: Optional[ClassificationRules] = None,
        path: Path = CLASSIFICATION_RULES_PATH,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the classifier with rules, loaded from a YAML file when not given.

        Args:
            rules (Optional[ClassificationRules]): The classification rules.
            path (Path): The YAML rules file, read when no rules are given.
            logger (Optional[Logger]): The classifier logger.

        Raises:
            ClassificationRulesFileError: If the rules file cannot be loaded.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rules = rules if rules else self._load(path)
        self.name_rules: List[CompiledTypeRule] = [
            (re.compile(rule.pattern, re.IGNORECASE), list(rule.types)) for rule in self.rules.name_rules
        ]
        self.category_rules: List[CompiledTypeRule] = [
            (re.compile(rule.pattern, re.IGNORECASE), list(rule.types)) for rule in self.rules.category_rules
        ]
        self.keyword_rules: List[CompiledTypeRule] = [
            (re.compile(rule.pattern, re.IGNORECASE), list(rule.types)) for rule in self.rules.keyword_rules
        ]
        suffix = self.rules.packaging_suffix
        self.packaging_suffix = re.compile(suffix, re.IGNORECASE) if suffix else None
        self.category_hints: List[CompiledCategoryHint] = [
            (re.compile(hint.pattern, re.IGNORECASE), list(hint.categories)) for hint in self.rules.category_hints
        ]
        self.logger.debug(
            "Software classifier ready: %d name rules, %d category rules, %d keyword rules, %d category hints.",
            len(self.name_rules),
            len(self.category_rules),
            len(self.keyword_rules),
            len(self.category_hints),
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _load(self, path: Path) -> ClassificationRules:
        """Load and validate the YAML classification rules.

        Args:
            path (Path): The YAML rules file.

        Returns:
            ClassificationRules: The validated rules.

        Raises:
            ClassificationRulesFileError: If the file cannot be read, is not valid YAML, or holds invalid rules.
        """
        self.logger.debug("Loading the classification rules %s.", path)
        try:
            with path.open(encoding="utf-8") as file:
                return ClassificationRules.model_validate(yaml.safe_load(file))
        except OSError as e:
            self.logger.error("The classification rules %s cannot be read: %s", path, e.strerror)
            raise ClassificationRulesFileError(path, f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The classification rules %s are not valid YAML.", path)
            raise ClassificationRulesFileError(path, f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The classification rules %s are invalid (%d errors).", path, e.error_count())
            raise ClassificationRulesFileError(path, f"the rules are invalid.\n{e}") from e

    def _normalize(self, text: str) -> str:
        """Normalize a marketplace category, so that `human-resources/talent_acquisition` reads as words.

        Args:
            text (str): The marketplace category.

        Returns:
            str: The category, case-folded, with the separators replaced by spaces.
        """
        return " ".join(re.sub(r"[-_/>|]+", " ", text.casefold()).split())

    def _product_name(self, name: str) -> str:
        """Remove the packaging suffix of a software name, e.g. ` on Ubuntu 24.04`.

        Args:
            name (str): The software name.

        Returns:
            str: The name without its packaging suffix, the whole name when nothing would be left.
        """
        if self.packaging_suffix is None:
            return name
        return self.packaging_suffix.sub("", name).strip() or name

    def _matching_types(self, rules: Sequence[CompiledTypeRule], texts: Iterable[str]) -> List[SoftwareType]:
        """Get the types given by the rules matching some texts.

        Args:
            rules (Sequence[CompiledTypeRule]): The compiled rules.
            texts (Iterable[str]): The texts.

        Returns:
            List[SoftwareType]: The types of every matching rule, in enum order.
        """
        found = {kind for text in texts if text for pattern, types in rules if pattern.search(text) for kind in types}
        return [kind for kind in SoftwareType if kind in found]

    ############################
    # Publicly Exposed Methods #
    ############################

    def classify(
        self,
        name: str,
        description: str,
        marketplace_categories: Sequence[str],
        delivery: DeliveryMethod = DeliveryMethod.OTHER,
    ) -> Tuple[List[SoftwareCategory], List[SoftwareType]]:
        """Classify a marketplace software.

        Args:
            name (str): The software name.
            description (str): The software description.
            marketplace_categories (Sequence[str]): The categories given by the marketplace itself.
            delivery (DeliveryMethod): How the software is delivered.

        Returns:
            Tuple[List[SoftwareCategory], List[SoftwareType]]: Its categories and types, in enum order, never empty.
        """
        labels = [self._normalize(label) for label in marketplace_categories]
        product = self._product_name(name)
        listed = self._matching_types(self.category_rules, labels)
        named = self._matching_types(self.keyword_rules, [product])
        described = self._matching_types(self.keyword_rules, [description])
        confirmed = [kind for kind in listed if kind in (named or described)]
        over_ticked = len(listed) > self.OVER_TICKED
        types = (
            self._matching_types(self.name_rules, [product])
            or (confirmed if over_ticked else [])
            or [kind for kind in SoftwareType if kind in listed or kind in named]
            or described
            or [SoftwareType.OTHER]
        )
        found = {category for kind in types for category in self.rules.type_categories[kind]}
        found.update(
            category
            for label in labels
            for pattern, hinted in self.category_hints
            if pattern.search(label)
            for category in hinted
        )
        if not found:
            found.update(self.rules.delivery_categories[delivery])
        categories = [category for category in SoftwareCategory if category in found]
        self.logger.debug("%r classified as %s, %s.", name, [str(c) for c in categories], [str(t) for t in types])
        return categories, types
