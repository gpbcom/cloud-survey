from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.prices.coverage.coverage_statement import CoverageStatement
from models.cloud.prices.exception import (
    InvalidCoverageLinksError,
    InvalidCoveragePagesError,
    InvalidCoverageRowLinksError,
    InvalidCoverageStatementsError,
    InvalidCurrencyError,
    InvalidProviderError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class CoverageCatalog(BaseModel):
    """The curated price coverage of a provider: which priced services price which products, and the statements.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        provider (CloudProvider): The cloud provider.
        links (Dict[str, List[str]]): The regular expressions matching the priced services (by name, or by their
            product detail) of each catalogue product, by product name.
        row_links (Dict[str, List[str]]): The regular expressions (PostgreSQL syntax, case ignored) matching the
            prices of each catalogue product by their row (`<service> | <sku_key> | <attributes as JSON>`, e.g. a
            SKU description), for the products priced within another service's prices (e.g. the GPUs of a compute
            service, an archive class of an object storage), by product name.
        statements (List[CoverageStatement]): How the products without price of their own are charged.
        pages (Dict[str, List[str]]): The public price pages of each product the crawler does not reach by itself
            (a price page missing from the provider's price index, a documentation price page), by product name.
        currency (str): The currency of the free products' zero price (the provider's price currency).

    Notes:
        It is read from `conf/prices/coverage/<provider>.yaml`. The row links are applied first, then the links,
        before the automatic name matching of `PriceLinker`. The statements become prices (free) or explicit
        unpriced rows. The price pages are read by the provider's crawler as product pages (their price tables,
        else the prices written in their text), their prices named after the product.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The cloud provider.")
    links: Dict[str, List[str]] = Field(default_factory=dict, description="The service patterns of each product.")
    row_links: Dict[str, List[str]] = Field(default_factory=dict, description="The row patterns of each product.")
    statements: List[CoverageStatement] = Field(default_factory=list, description="The coverage statements.")
    pages: Dict[str, List[str]] = Field(default_factory=dict, description="The extra price pages of each product.")
    currency: str = Field(default="USD", description="The currency of the free products' zero price.")

    @field_validator("provider", mode="before")
    def validate_provider(cls, value: RawValue) -> RawValue:
        """Validate the raw cloud provider: a `CloudProvider` value.

        Args:
            value (RawValue): The raw cloud provider.

        Returns:
            RawValue: The checked cloud provider.

        Raises:
            InvalidProviderError: If it is not a `CloudProvider` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in CloudProvider])
        except PriceCheckError as e:
            raise InvalidProviderError(e.value, e.expected) from e

    @field_validator("links", mode="before")
    def validate_links(cls, value: RawValue) -> RawValue:
        """Validate the raw links: product names mapped to lists of valid regular expressions.

        Args:
            value (RawValue): The raw links.

        Returns:
            RawValue: The checked links.

        Raises:
            InvalidCoverageLinksError: If it is not such a mapping.
        """
        if value is None:
            return {}
        try:
            links = cls.CHECK.mapping(value)
            for product, patterns in links.items():
                cls.CHECK.text(product, 300)
                for pattern in cls.CHECK.items(patterns):
                    re.compile(str(cls.CHECK.text(pattern, 500, collapse=False)))
        except PriceCheckError as e:
            raise InvalidCoverageLinksError(e.value, e.expected) from e
        except re.error as e:
            raise InvalidCoverageLinksError(str(e.pattern), "valid regular expressions") from e
        return links

    @field_validator("row_links", mode="before")
    def validate_row_links(cls, value: RawValue) -> RawValue:
        """Validate the raw row links: product names mapped to lists of valid regular expressions.

        Args:
            value (RawValue): The raw row links.

        Returns:
            RawValue: The checked row links.

        Raises:
            InvalidCoverageRowLinksError: If it is not such a mapping.
        """
        if value is None:
            return {}
        try:
            links = cls.CHECK.mapping(value)
            for product, patterns in links.items():
                cls.CHECK.text(product, 300)
                for pattern in cls.CHECK.items(patterns):
                    re.compile(str(cls.CHECK.text(pattern, 500, collapse=False)))
        except PriceCheckError as e:
            raise InvalidCoverageRowLinksError(e.value, e.expected) from e
        except re.error as e:
            raise InvalidCoverageRowLinksError(str(e.pattern), "valid regular expressions") from e
        return links

    @field_validator("statements", mode="before")
    def validate_statements(cls, value: RawValue) -> RawValue:
        """Validate the raw statements: a list (each statement validates its own fields).

        Args:
            value (RawValue): The raw statements.

        Returns:
            RawValue: The checked statements.

        Raises:
            InvalidCoverageStatementsError: If it is not a list.
        """
        if value is None:
            return []
        try:
            return cls.CHECK.items(value)
        except PriceCheckError as e:
            raise InvalidCoverageStatementsError(e.value, e.expected) from e

    @field_validator("pages", mode="before")
    def validate_pages(cls, value: RawValue) -> RawValue:
        """Validate the raw price pages: product names mapped to lists of http(s) URLs.

        Args:
            value (RawValue): The raw price pages.

        Returns:
            RawValue: The checked price pages.

        Raises:
            InvalidCoveragePagesError: If it is not such a mapping.
        """
        if value is None:
            return {}
        try:
            pages = cls.CHECK.mapping(value)
            for product, urls in pages.items():
                cls.CHECK.text(product, 300)
                for url in cls.CHECK.items(urls):
                    cls.CHECK.url(url)
        except PriceCheckError as e:
            raise InvalidCoveragePagesError(e.value, e.expected) from e
        return pages

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: RawValue) -> RawValue:
        """Validate the raw currency: an ISO 4217 code.

        Args:
            value (RawValue): The raw currency.

        Returns:
            RawValue: The checked currency.

        Raises:
            InvalidCurrencyError: If it is not an ISO 4217 code.
        """
        try:
            return cls.CHECK.currency(value, optional=False)
        except PriceCheckError as e:
            raise InvalidCurrencyError(e.value, e.expected) from e
