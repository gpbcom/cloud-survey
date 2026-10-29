from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.data.dated_product import DatedProduct
from models.compounding.data.year_value import YearValue


class CompoundingData(BaseModel):
    """Everything the compounding models read from the database.

    Attributes:
        products (List[DatedProduct]): The dated products of the providers analysed and excluded.
        shares (List[YearValue]): The yearly cloud-market shares of the providers.
        market (List[YearValue]): The yearly sizes of the worldwide cloud infrastructure services market.
        snapshot (Dict[CloudProvider, List[str]]): The cloud computing categories every catalogue offers today (dated
            or not), for the proximity of the categories.
        categories (List[str]): Every category of the kept domains.

    Notes:
        It is read by `analytics.compounding.data.compounding_loader.CompoundingLoader` and fitted by
        `analytics.compounding.compounding_analysis.CompoundingAnalysis`, which never opens the database.
    """

    model_config = ConfigDict(frozen=True)

    products: List[DatedProduct] = Field(default_factory=list, description="The dated products.")
    shares: List[YearValue] = Field(default_factory=list, description="The yearly cloud-market shares.")
    market: List[YearValue] = Field(default_factory=list, description="The yearly market sizes.")
    snapshot: Dict[CloudProvider, List[str]] = Field(default_factory=dict, description="Today's categories.")
    categories: List[str] = Field(default_factory=list, description="Every category of the kept domains.")
