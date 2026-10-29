from __future__ import annotations

import asyncio
import math
from datetime import date
from typing import List
from unittest.mock import AsyncMock, MagicMock

import numpy
import pytest

from analytics.compounding.compounding_analysis import CompoundingAnalysis
from analytics.compounding.config_loader import CompoundingConfigLoader
from analytics.compounding.data.compounding_loader import CompoundingLoader
from analytics.compounding.exception import CompoundingFileError, UnknownCompoundingSlugError
from analytics.compounding.help_loader import CompoundingHelpLoader
from curated.bundle.bundle_catalogs import BundleCatalogs
from models.cloud.enums import CloudProvider, MarketRegion, MarketSegment
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.data.dated_product import DatedProduct
from models.compounding.data.year_value import YearValue
from models.compounding.enums import (
    CompoundingCard,
    CompoundingColumn,
    CompoundingControl,
    CompoundingWarningKind,
    CurveKind,
    FoundationSource,
    Specification,
    ValueOrigin,
    Verdict,
)
from models.markets.enums import ShareMetric, ShareSource
from models.markets.values.market_share_value import MarketShareValue
from models.stats.market_report import MarketReport
from taxonomy.seed_loader import TaxonomySeedLoader


def test_the_shipped_configuration_names_taxonomy_slugs_only() -> None:
    config = CompoundingConfigLoader().load(taxonomy=TaxonomySeedLoader().load_taxonomy())

    assert CloudProvider.AWS in config.kept()
    assert all(entry.links for entry in config.foundations)


def test_an_unknown_category_is_refused(tmp_path, compounding_config: CompoundingConfig) -> None:
    path = tmp_path / "compounding.yaml"
    path.write_text(
        "providers: [{provider: amazon-web-services}]\ndomains: [compute]\n"
        "foundations: [{category: not-a-category, links: [{foundation: virtual-machines, source: 'https://x.y'}]}]\n",
        encoding="utf-8",
    )

    with pytest.raises(UnknownCompoundingSlugError):
        CompoundingConfigLoader().load(path, TaxonomySeedLoader().load_taxonomy())


def test_an_invalid_configuration_is_reported(tmp_path) -> None:
    path = tmp_path / "compounding.yaml"
    path.write_text("providers: []\ndomains: [compute]\n", encoding="utf-8")

    with pytest.raises(CompoundingFileError):
        CompoundingConfigLoader().load(path)


@pytest.mark.parametrize(
    ("group", "values"),
    [
        ("controls", list(CompoundingControl)),
        ("columns", list(CompoundingColumn)),
        ("warnings", list(CompoundingWarningKind)),
        ("verdicts", list(Verdict)),
        ("curves", list(CurveKind)),
        ("cards", list(CompoundingCard)),
        ("choices", [*Specification, *FoundationSource]),
    ],
)
def test_every_control_choice_column_warning_verdict_curve_and_card_is_explained(group: str, values: List[str]) -> None:
    help_texts = CompoundingHelpLoader().load()

    assert [value for value in values if help_texts.entry(group, str(value)) is None] == []


def test_the_analysis_fits_every_provider_and_the_pooled_fit(
    compounding_data: CompoundingData, compounding_config: CompoundingConfig
) -> None:
    report = CompoundingAnalysis(compounding_config).run(CompoundingQuery(), compounding_data)

    assert [row.provider for row in report.coverage] == [CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP]
    assert report.summary[-1].provider is None
    assert {fit.provider for fit in report.hazard} == {CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP, None}
    assert report.foundations == {"kubernetes": ["virtual-machines"], "data-lake": ["object-storage"]}
    assert len(report.lags) == 4
    assert any(warning.kind is CompoundingWarningKind.NO_DATA for warning in report.warnings)


def test_the_data_driven_and_share_specifications_run(
    compounding_data: CompoundingData, compounding_config: CompoundingConfig
) -> None:
    analysis = CompoundingAnalysis(compounding_config)

    driven = analysis.run(CompoundingQuery(source=FoundationSource.DATA_DRIVEN), compounding_data)
    shared = analysis.run(CompoundingQuery(specification=Specification.SHARE), compounding_data)

    assert driven.query.source is FoundationSource.DATA_DRIVEN
    assert any(warning.kind is CompoundingWarningKind.NO_SHARE for warning in shared.warnings)


def test_a_strong_foundation_effect_supports_the_hypothesis(compounding_config: CompoundingConfig) -> None:
    generator = numpy.random.default_rng(4)
    categories = [f"c{index}" for index in range(40)]
    foundations = {f"c{index}": [f"c{index - 20}"] for index in range(20, 40)}
    config = compounding_config.model_copy(
        update={
            "foundations": [
                compounding_config.foundations[0].model_copy(
                    update={
                        "category": dependent,
                        "links": [
                            compounding_config.foundations[0].links[0].model_copy(update={"foundation": found[0]})
                        ],
                    }
                )
                for dependent, found in foundations.items()
            ],
            "settings": compounding_config.settings.model_copy(
                update={"placebo": 40, "bootstrap": 40, "min_events": 5, "last_year": 2025}
            ),
        }
    )
    products: List[DatedProduct] = []
    for provider in (CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP):
        for index in range(20):
            year = int(generator.integers(2011, 2023))
            products.append(DatedProduct(provider=provider, year=year, categories=[f"c{index}"]))
            products.append(DatedProduct(provider=provider, year=year + 1, categories=[f"c{index + 20}"]))
    data = CompoundingData(
        products=products,
        market=[
            YearValue(year=year, value=10.0 * 1.2 ** (year - 2009), origin=ValueOrigin.CRAWLED)
            for year in range(2009, 2026)
        ],
        snapshot={},
        categories=categories,
    )

    report = CompoundingAnalysis(config).run(CompoundingQuery(), data)

    pooled = next(fit for fit in report.hazard if fit.provider is None)
    foundations_estimate = pooled.estimate("foundations")
    assert foundations_estimate is not None
    assert foundations_estimate.significant()
    assert foundations_estimate.value > 0
    placebo = next(test for test in report.placebo if test.provider is None)
    assert placebo.p_value is not None
    assert placebo.p_value < 0.1


def test_the_loader_reads_the_shares_and_the_market_sizes(compounding_config: CompoundingConfig) -> None:
    chronology = BundleCatalogs().chronology()
    loader = CompoundingLoader(compounding_config, chronology)
    day = date
    shares = [
        MarketShareValue(
            segment="cloud",
            area="ww",
            period=day(2018, 1, 1),
            metric=ShareMetric.REVENUE,
            source=ShareSource.SYNERGY,
            label="Amazon",
            company="amazon",
            value=33.0,
        ),
        MarketShareValue(
            segment="cloud",
            area="ww",
            period=day(2018, 4, 1),
            metric=ShareMetric.REVENUE,
            source=ShareSource.SYNERGY,
            label="Amazon",
            company="amazon",
            value=35.0,
        ),
        MarketShareValue(
            segment="cloud",
            area="ww",
            period=day(2018, 1, 1),
            metric=ShareMetric.REVENUE,
            source=ShareSource.MANUAL,
            label="Amazon",
            company="amazon",
            value=10.0,
        ),
        MarketShareValue(
            segment="cloud",
            area="ww",
            period=day(2012, 1, 1),
            metric=ShareMetric.REVENUE,
            source=ShareSource.MANUAL,
            label="Amazon",
            company="amazon",
            value=20.0,
        ),
    ]
    reports = [
        MarketReport(
            period=period,
            region=MarketRegion.WORLDWIDE,
            segment=MarketSegment.CLOUD_INFRASTRUCTURE,
            market_size_bn=size,
            source_url="https://www.srgresearch.com/articles/x",
            title="x",
            published=day(2020, 1, 1),
        )
        for period, size in (
            ("2018Q1", 10.0),
            ("2018Q2", 11.0),
            ("2018Q4", 13.0),
            ("2019Q1", 14.0),
            ("2019Q2", 15.0),
            ("2019Q3", 16.0),
            ("2019Q4", 17.0),
        )
    ]
    storage = MagicMock()
    storage.taxonomy.list = AsyncMock(return_value=TaxonomySeedLoader().load_taxonomy())
    storage.catalogues.items = AsyncMock(return_value=None)
    storage.shares.list = AsyncMock(return_value=shares)
    storage.statistics.read = AsyncMock(return_value=MagicMock(reports=reports))

    data = asyncio.run(loader.load(storage))

    by_year = {(share.year, share.origin): share.value for share in data.shares}
    assert by_year == {(2018, ValueOrigin.CRAWLED): 34.0, (2012, ValueOrigin.MANUAL): 20.0}
    sizes = {point.year: point for point in data.market}
    assert sizes[2019].value == 62.0
    assert sizes[2019].origin is ValueOrigin.CRAWLED
    assert sizes[2018].origin is ValueOrigin.INTERPOLATED
    assert sizes[2018].value == pytest.approx(10 + 11 + math.sqrt(11 * 13) + 13)
