from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from enum import Enum
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import orjson
import xxhash
from pydantic import BaseModel

# First Party Imports.
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from storage.repositories.prices.staged_merge import StagedValue


class PriceRecords:
    """Write the prices and free offers a crawl read as the rows copied into the staging tables, with their hash.

    Attributes:
        PRICE_COLUMNS (ClassVar[List[str]]): The columns of a price, in the order of a copied row.
        PRICE_IGNORED (ClassVar[List[str]]): The fields of a price left out of its fingerprint (where it was read, not
            what it is).
        FREE_COLUMNS (ClassVar[List[str]]): The columns of a free offer, in the order of a copied row.
        FREE_IGNORED (ClassVar[List[str]]): The fields of a free offer left out of its fingerprint.
        logger (Logger): The writer logger.

    Notes:
        The fingerprint is the xxHash64 of the canonical JSON
        of the fields that make the price (the decimals
        normalized, the keys sorted): a price read again unchanged
        has the same fingerprint, so the merge leaves its
        row as it is, even when the page it is read from moved.
        The writer runs once per price read (millions for a large provider): it only logs at the debug level.
    """

    PRICE_COLUMNS: ClassVar[List[str]] = [
        "provider",
        "sku_key",
        "service",
        "family",
        "region",
        "instance_type",
        "vcpu",
        "memory_gib",
        "storage_gib",
        "os",
        "attributes",
        "unit",
        "unit_raw",
        "unit_factor",
        "price",
        "currency",
        "model",
        "term",
        "tier_start",
        "tier_end",
        "billing_increment_s",
        "minimum_quantity",
        "minimum_duration_days",
        "effective_from",
        "source_url",
        "source_kind",
        "captured",
        "reason",
        "fingerprint",
    ]
    PRICE_IGNORED: ClassVar[List[str]] = ["source_url", "source_kind", "captured", "effective_from"]
    FREE_COLUMNS: ClassVar[List[str]] = [
        "provider",
        "free_key",
        "service",
        "kind",
        "quantity",
        "unit",
        "unit_raw",
        "currency",
        "period",
        "duration_days",
        "region_scope",
        "conditions",
        "source_url",
        "source_kind",
        "fingerprint",
    ]
    FREE_IGNORED: ClassVar[List[str]] = ["source_url", "source_kind"]

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the writer.

        Args:
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _canonical(self, value: StagedValue) -> StagedValue:
        """Write a field value the same way whatever its form (`1.50` and `1.5` are one price).

        Args:
            value (StagedValue): The value.

        Returns:
            StagedValue: The value, a decimal as its normalized text, an enumeration as its value.
        """
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        if isinstance(value, Enum):
            return str(value.value)
        return value

    def _values(self, fact: BaseModel, columns: List[str]) -> List[StagedValue]:
        """Read the values of the columns of a fact, as copied.

        Args:
            fact (BaseModel): The price or the free offer.
            columns (List[str]): The columns, the fingerprint excluded.

        Returns:
            List[StagedValue]: Its values: the enumerations as their values, the JSON objects as JSON text (keys
                sorted).
        """
        values: List[StagedValue] = []
        for name in columns:
            raw = getattr(fact, name)
            if isinstance(raw, dict):
                values.append(orjson.dumps(raw, option=orjson.OPT_SORT_KEYS).decode())
            elif isinstance(raw, Enum):
                values.append(str(raw.value))
            else:
                values.append(raw)
        return values

    def _hash(self, columns: List[str], values: List[StagedValue], ignored: List[str]) -> str:
        """Hash the values that make a fact.

        Args:
            columns (List[str]): The columns of the values.
            values (List[StagedValue]): The values.
            ignored (List[str]): The columns left out (where it was read, not what it is).

        Returns:
            str: The xxHash64 of their canonical JSON, in hexadecimal.
        """
        kept = [self._canonical(value) for name, value in zip(columns, values, strict=True) if name not in ignored]
        return xxhash.xxh64(orjson.dumps(kept, default=str)).hexdigest()

    ############################
    # Publicly Exposed Methods #
    ############################

    def price_fingerprint(self, price: ServicePrice) -> str:
        """Hash the fields that make a price.

        Args:
            price (ServicePrice): The price.

        Returns:
            str: Its fingerprint.
        """
        columns = self.PRICE_COLUMNS[:-1]
        fingerprint = self._hash(columns, self._values(price, columns), self.PRICE_IGNORED)
        self.logger.debug("Fingerprint of the price %s: %s.", price.sku_key, fingerprint)
        return fingerprint

    def free_fingerprint(self, tier: FreeTier) -> str:
        """Hash the fields that make a free offer.

        Args:
            tier (FreeTier): The free offer.

        Returns:
            str: Its fingerprint.
        """
        columns = self.FREE_COLUMNS[:-1]
        fingerprint = self._hash(columns, self._values(tier, columns), self.FREE_IGNORED)
        self.logger.debug("Fingerprint of the free offer %s: %s.", tier.free_key, fingerprint)
        return fingerprint

    def price_record(self, price: ServicePrice) -> Tuple[StagedValue, ...]:
        """Write a price as a copied row, read in one pass with its fingerprint.

        Args:
            price (ServicePrice): The price.

        Returns:
            Tuple[StagedValue, ...]: Its values, in the order of `PRICE_COLUMNS` (the fingerprint last).
        """
        columns = self.PRICE_COLUMNS[:-1]
        values = self._values(price, columns)
        if price.price is None:
            self.logger.debug("The price %s has no public price (%s).", price.sku_key, price.model.value)
        return (*values, self._hash(columns, values, self.PRICE_IGNORED))

    def free_record(self, tier: FreeTier) -> Tuple[StagedValue, ...]:
        """Write a free offer as a copied row, read in one pass with its fingerprint.

        Args:
            tier (FreeTier): The free offer.

        Returns:
            Tuple[StagedValue, ...]: Its values, in the order of `FREE_COLUMNS` (the fingerprint last).
        """
        columns = self.FREE_COLUMNS[:-1]
        values = self._values(tier, columns)
        if tier.quantity is None:
            self.logger.debug("The free offer %s states no quantity.", tier.free_key)
        return (*values, self._hash(columns, values, self.FREE_IGNORED))
