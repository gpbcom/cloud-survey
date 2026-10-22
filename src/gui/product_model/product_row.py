from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.products.product import CloudProduct


@dataclass(frozen=True)
class ProductRow:
    """A product of the table, with its catalogue context.

    Attributes:
        provider (CloudProvider): The cloud provider of the product.
        product (CloudProduct): The product.
        crawled_at (Optional[datetime]): When the provider catalogue was last crawled, `None` when unknown.
        id (int): The storage identifier of the product.
    """

    provider: CloudProvider
    product: CloudProduct
    crawled_at: Optional[datetime]
    id: int = 0
