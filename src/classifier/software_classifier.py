from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Iterable, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from classifier.exception import ClassificationRulesFileError
from conf import CLASSIFICATION_RULES_PATH
from models.classification.category_rule import CategoryRule
from models.classification.classification import Classification
from models.classification.classification_rules import ClassificationRules
from models.cloud.enums import DeliveryMethod, SoftwareCategory
from models.taxonomy.nodes.taxonomy import Taxonomy
from taxonomy.seed_loader import TaxonomySeedLoader

CompiledRule = Tuple[re.Pattern[str], List[str]]
CompiledHint = Tuple[re.Pattern[str], List[SoftwareCategory]]


class SoftwareClassifier:
    """Classify the catalogue products and the marketplace software into the unified taxonomy, with rules.

    Attributes:
        OVER_TICKED (ClassVar[int]): Above this number of categories given by the source labels, a listing is deemed
            over-ticked: only the categories its keywords confirm are kept, when any.
        OTHER (ClassVar[str]): The category of the items nothing classifies.
        rules (ClassificationRules): The classification rules.
        taxonomy (Taxonomy): The taxonomy the rules name (its domains, the audiences of its nodes).
        name_rules (List[CompiledRule]): The compiled well-known product rules.
        category_rules (List[CompiledRule]): The compiled source label rules.
        keyword_rules (List[CompiledRule]): The compiled name and description rules.
        audience_hints (List[CompiledHint]): The compiled audience hints.
        noise_labels (List[re.Pattern[str]]): The compiled patterns of the labels which are not categories.
        packaging_suffix (Optional[re.Pattern[str]]): The compiled packaging suffix of the names, if any.
        logger (Logger): The classifier logger.

    Notes:
        - The categories of an item are, in this order of precedence:
            1. those of a well-known product (name rules),
            2. for over-ticked source labels (more than `OVER_TICKED` categories and domains), the label
               categories its keywords confirm (name and description) with those of its name, else all its keyword
               categories,
            3. those of its source labels together with the keyword categories of its name,
            4. the keyword categories of its description within the domains its labels only tell, else all of them,
            5. the categories of its delivery method (software only),
            6. else `other`.
        - The categories of the source labels are given by the caller (the links stored in the database) or, without
          them, by the label rules. A label may only tell a domain: the item then belongs to that domain without a
          category of it, which is not `other`.
        - A keyword confirms an over-ticked label category of the same domain (the more specific category is kept),
          and an umbrella category (e.g. `security`) is refined by the description keywords of its domain (e.g.
          `network-security` for a firewall), and dropped next to a more specific one of its domain.
        - The names are matched without their packaging suffix (e.g. ` on Ubuntu 24.04`, ` Virtual Machine`).
        - The audiences are those of the categories and domains, plus the ones hinted by the labels, else those of
          the delivery method (software) or of the products.
    """

    OVER_TICKED: ClassVar[int] = 2
    OTHER: ClassVar[str] = "other"

    def __init__(
        self,
        rules: Optional[ClassificationRules] = None,
        path: Path = CLASSIFICATION_RULES_PATH,
        taxonomy: Optional[Taxonomy] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the classifier with rules and a taxonomy, loaded from the project files when not given.

        Args:
            rules (Optional[ClassificationRules]): The classification rules.
            path (Path): The YAML rules file, read when no rules are given.
            taxonomy (Optional[Taxonomy]): The taxonomy, the seed of the project when not given.
            logger (Optional[Logger]): The classifier logger.

        Raises:
            ClassificationRulesFileError: If the rules file cannot be loaded.
            TaxonomySeedFileError: If the taxonomy seed cannot be loaded.
            UnknownTaxonomySlugError: If the rules name nodes the taxonomy does not hold.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rules = rules if rules else self._load(path)
        loader = TaxonomySeedLoader(self.logger)
        self.taxonomy = taxonomy if taxonomy else loader.load_taxonomy()
        loader.check(self.taxonomy, self.rules)
        self.name_rules = self._compile_rules(self.rules.name_rules)
        self.category_rules = self._compile_rules(self.rules.category_rules)
        self.keyword_rules = self._compile_rules(self.rules.keyword_rules)
        self.audience_hints: List[CompiledHint] = [
            (re.compile(hint.pattern, re.IGNORECASE), list(hint.audiences)) for hint in self.rules.audience_hints
        ]
        self.noise_labels = [re.compile(f"^(?:{pattern})$", re.IGNORECASE) for pattern in self.rules.noise_labels]
        suffix = self.rules.packaging_suffix
        self.packaging_suffix = re.compile(suffix, re.IGNORECASE) if suffix else None
        self.logger.debug(
            "Classifier ready: %d name rules, %d label rules, %d keyword rules over %d taxonomy nodes.",
            len(self.name_rules),
            len(self.category_rules),
            len(self.keyword_rules),
            len(self.taxonomy.nodes),
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

    def _compile_rules(self, rules: Iterable[CategoryRule]) -> List[CompiledRule]:
        """Compile category rules.

        Args:
            rules (Iterable[CategoryRule]): The rules.

        Returns:
            List[CompiledRule]: Their case-insensitive patterns and slugs.
        """
        return [(re.compile(rule.pattern, re.IGNORECASE), list(rule.categories)) for rule in rules]

    def _normalize(self, text: str) -> str:
        """Normalize a source label, so that `human-resources/talent_acquisition` reads as words.

        Args:
            text (str): The source label.

        Returns:
            str: The label, case-folded, with the separators replaced by spaces.
        """
        return " ".join(re.sub(r"[-_/>|]+", " ", text.casefold()).split())

    def _product_name(self, name: str) -> str:
        """Remove the packaging suffix of a name, e.g. ` on Ubuntu 24.04`.

        Args:
            name (str): The name.

        Returns:
            str: The name without its packaging suffix, the whole name when nothing would be left.
        """
        if self.packaging_suffix is None:
            return name
        return self.packaging_suffix.sub("", name).strip() or name

    def _matching(self, rules: Sequence[CompiledRule], texts: Iterable[str]) -> List[str]:
        """Get the slugs given by the rules matching some texts.

        Args:
            rules (Sequence[CompiledRule]): The compiled rules.
            texts (Iterable[str]): The texts.

        Returns:
            List[str]: The slugs of every matching rule, in taxonomy order.
        """
        found = {slug for text in texts if text for pattern, slugs in rules if pattern.search(text) for slug in slugs}
        return self.taxonomy.ordered(found)

    def _specific(self, categories: List[str]) -> List[str]:
        """Drop the umbrella categories of the domains where a more specific category applies.

        Args:
            categories (List[str]): The categories, in taxonomy order.

        Returns:
            List[str]: The categories, without an umbrella category next to a sibling (e.g. `security` next to
                `network-security`).
        """
        domains = [self.taxonomy.domain_of(slug) for slug in categories]
        kept: List[str] = []
        for slug, domain in zip(categories, domains, strict=True):
            node = self.taxonomy.node(slug)
            umbrella = node is not None and node.umbrella
            if not (umbrella and sum(1 for other in domains if other == domain) > 1):
                kept.append(slug)
        return kept

    def _categories(
        self,
        product: str,
        description: str,
        listed: List[str],
        delivery: Optional[DeliveryMethod],
        label_domains: List[str],
    ) -> List[str]:
        """Get the categories of an item, by order of precedence.

        Args:
            product (str): The name, without its packaging suffix.
            description (str): The description.
            listed (List[str]): The categories given by the source labels.
            delivery (Optional[DeliveryMethod]): How a software is delivered, `None` for a product.
            label_domains (List[str]): The domains the source labels give without a category.

        Returns:
            List[str]: The categories, in taxonomy order, empty when only domains are known, `other` when nothing is.
        """
        named = self._matching(self.keyword_rules, [product])
        described = self._matching(self.keyword_rules, [description])
        keywords = [*named, *described]
        listed_domains = {self.taxonomy.domain_of(slug) for slug in listed} | set(label_domains)
        confirmed = [slug for slug in listed if slug in keywords] + [
            slug for slug in keywords if self.taxonomy.domain_of(slug) in listed_domains
        ]
        within = [slug for slug in described if self.taxonomy.domain_of(slug) in label_domains]
        found = (
            self._matching(self.name_rules, [product])
            or (
                (self.taxonomy.ordered([*confirmed, *named]) or self.taxonomy.ordered(keywords))
                if len(listed) + len(label_domains) > self.OVER_TICKED
                else []
            )
            or self.taxonomy.ordered([*listed, *named])
            or within
            or described
        )
        umbrellas = {
            self.taxonomy.domain_of(slug) for slug in found if (node := self.taxonomy.node(slug)) and node.umbrella
        }
        refined = [slug for slug in described if self.taxonomy.domain_of(slug) in umbrellas]
        if found or label_domains:
            categories = self.taxonomy.ordered([*found, *refined])
            return self._specific([slug for slug in categories if self.taxonomy.is_category(slug)])
        fallback = self.rules.delivery_categories.get(delivery, []) if delivery is not None else []
        return self.taxonomy.ordered(fallback) or [self.OTHER]

    def _audiences(self, nodes: Iterable[str], labels: Sequence[str]) -> Set[SoftwareCategory]:
        """Get the audiences of taxonomy nodes and of the hints of the source labels.

        Args:
            nodes (Iterable[str]): The categories and domains.
            labels (Sequence[str]): The normalized source labels.

        Returns:
            Set[SoftwareCategory]: The audiences found, empty when none.
        """
        found = {audience for slug in nodes for audience in self.taxonomy.audiences_of(slug)}
        found.update(
            audience
            for label in labels
            for pattern, hinted in self.audience_hints
            if pattern.search(label)
            for audience in hinted
        )
        return found

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_noise(self, label: str) -> bool:
        """Tell whether a source label is not a category (a tab, a vendor name, "Other").

        Args:
            label (str): The source label.

        Returns:
            bool: Whether a noise pattern matches the whole label.
        """
        normalized = self._normalize(label)
        return any(pattern.match(normalized) for pattern in self.noise_labels)

    def label_categories(self, label: str) -> List[str]:
        """Get the taxonomy nodes the rules give to a source label.

        Args:
            label (str): The source label.

        Returns:
            List[str]: The categories and domains of the matching label rules, in taxonomy order, empty for noise.
        """
        if self.is_noise(label):
            return []
        return self._matching(self.category_rules, [self._normalize(label)])

    def classify(
        self,
        name: str,
        description: str,
        labels: Sequence[str],
        delivery: Optional[DeliveryMethod] = DeliveryMethod.OTHER,
        label_nodes: Optional[Sequence[Sequence[str]]] = None,
    ) -> Classification:
        """Classify an item.

        Args:
            name (str): Its name.
            description (str): Its description.
            labels (Sequence[str]): Its source labels (the categories given by the provider).
            delivery (Optional[DeliveryMethod]): How a software is delivered, `None` for a catalogue product.
            label_nodes (Optional[Sequence[Sequence[str]]]): The taxonomy nodes of each label (stored links), `None`
                to match the label rules instead.

        Returns:
            Classification: Its audiences, categories and domains.
        """
        kept = [label for label in labels if not self.is_noise(label)]
        normalized = [self._normalize(label) for label in kept]
        if label_nodes is None:
            nodes = self._matching(self.category_rules, normalized)
        else:
            nodes = self.taxonomy.ordered(slug for slugs in label_nodes for slug in slugs)
        listed = [slug for slug in nodes if self.taxonomy.is_category(slug)]
        label_domains = [slug for slug in nodes if self.taxonomy.is_domain(slug)]
        categories = self._categories(self._product_name(name), description, listed, delivery, label_domains)
        domains = self.taxonomy.ordered(
            [domain for slug in categories if (domain := self.taxonomy.domain_of(slug))] + label_domains
        )
        found = self._audiences([*categories, *label_domains], normalized)
        if not found and delivery is not None:
            found = set(self.rules.delivery_audiences[delivery])
        elif not found:
            found = set(self.rules.product_audiences) or set(self.rules.delivery_audiences[DeliveryMethod.OTHER])
        classification = Classification(
            audiences=[audience for audience in SoftwareCategory if audience in found],
            categories=categories,
            domains=domains,
        )
        self.logger.debug("%r classified as %s.", name, classification.categories or classification.domains)
        return classification

    def classify_product(
        self,
        name: str,
        description: str,
        catalogue_categories: Sequence[str],
        label_nodes: Optional[Sequence[Sequence[str]]] = None,
    ) -> Classification:
        """Classify a cloud catalogue product: the same rules as the software, without delivery method.

        Args:
            name (str): The product name.
            description (str): The product description.
            catalogue_categories (Sequence[str]): The categories the catalogue of the provider files it under.
            label_nodes (Optional[Sequence[Sequence[str]]]): The taxonomy nodes of each label (stored links), `None`
                to match the label rules instead.

        Returns:
            Classification: Its audiences, categories and domains.
        """
        return self.classify(name, description, catalogue_categories, None, label_nodes)
