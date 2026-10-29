from __future__ import annotations

from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.catalog_checks import CatalogChecks
from models.companies.companies_catalog import CompaniesCatalog
from models.markets.markets_catalog import MarketsCatalog


def test_the_shipped_catalogues_name_only_chronology_companies(
    companies_catalog: CompaniesCatalog, markets_catalog: MarketsCatalog
) -> None:
    checks = CatalogChecks()
    chronology = BundleCatalogs().chronology()

    assert checks.unknown_companies(companies_catalog, chronology) == []
    assert checks.unknown_market_companies(markets_catalog, chronology) == []
    assert checks.unknown_figure_companies(BundleCatalogs().figures(), chronology) == []
    assert checks.unknown_segment_links(markets_catalog, chronology) == []


def test_a_company_outside_the_chronology_is_reported(
    companies_catalog: CompaniesCatalog, markets_catalog: MarketsCatalog
) -> None:
    checks = CatalogChecks()
    chronology = BundleCatalogs().chronology()
    smaller = chronology.model_copy(
        update={"companies": [company for company in chronology.companies if company.key != "ibm"]}
    )

    assert "ibm" in checks.unknown_companies(companies_catalog, smaller)
    assert "ibm" in checks.unknown_market_companies(markets_catalog, smaller)
    assert "ibm" not in checks.uncrawled_companies(companies_catalog, smaller)
    assert checks.uncrawled_companies(companies_catalog, chronology) == sorted(
        {company.key for company in chronology.companies} - {entry.key for entry in companies_catalog.companies}
    )
