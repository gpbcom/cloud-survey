from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from datetime import datetime

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.product import CloudProduct


@dataclass(frozen=True)
class ProductRow:
    """A product of the table, with its catalogue context.

    Attributes:
        provider (CloudProvider): The cloud provider of the product.
        product (CloudProduct): The product.
        crawled_at (datetime): When the provider catalogue was crawled.
    """

    provider: CloudProvider
    product: CloudProduct
    crawled_at: datetime
