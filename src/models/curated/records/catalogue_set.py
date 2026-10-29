from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.companies.companies_catalog import CompaniesCatalog
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class CatalogueSet(BaseModel):
    """The curated catalogues the explorer's views are built from: the chronology, the markets and the companies.

    Attributes:
        chronology (Chronology): The leaders and the notable events, which name and colour the companies.
        markets (MarketsCatalog): The segments, areas, listings and valuations of the market cards.
        companies (CompaniesCatalog): The companies whose financials, patents and papers are read.

    Notes:
        The views are built from the bundle, then from the database once it is read (where the edits of the
        Catalogues manager are), when the two differ.
    """

    model_config = ConfigDict(frozen=True)

    chronology: Chronology = Field(description="The leaders and the notable events.")
    markets: MarketsCatalog = Field(description="The markets catalogue.")
    companies: CompaniesCatalog = Field(description="The companies catalogue.")
