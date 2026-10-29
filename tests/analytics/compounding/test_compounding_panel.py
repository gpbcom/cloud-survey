from __future__ import annotations

import math

import numpy
import pytest

from analytics.compounding.data.covariates.category_density import CategoryDensity
from analytics.compounding.data.covariates.foundation_share import FoundationShare
from analytics.compounding.data.entry_panel import EntryPanel
from analytics.compounding.data.risk_set_builder import RiskSetBuilder
from models.cloud.enums import CloudProvider
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.enums import FitKind, Specification

AWS, AZURE, GCP = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP
VM, K8S, OBJECT, LAKE = 0, 1, 2, 3


@pytest.fixture
def panel(compounding_data: CompoundingData, compounding_config: CompoundingConfig) -> EntryPanel:
    return EntryPanel(compounding_data, compounding_config).build()


def test_the_window_starts_with_the_public_cloud_or_the_first_launch(panel: EntryPanel) -> None:
    assert panel.windows[AWS] == (2010, 2016)
    assert panel.windows[AZURE] == (2011, 2016)
    assert panel.windows[GCP] == (2011, 2016)


def test_a_product_dated_before_the_window_or_on_or_before_is_held_at_the_start(panel: EntryPanel) -> None:
    assert panel.entries[AWS][VM] == 2010
    assert panel.held[AWS] == 1
    assert panel.entries[AZURE][OBJECT] == 2011
    assert panel.launches[AZURE][2013] == 0


def test_the_catalogue_size_and_the_launches_follow_the_dates(panel: EntryPanel) -> None:
    assert [panel.size(AWS, year) for year in range(2010, 2016)] == [1, 2, 2, 3, 4, 4]
    assert panel.launches[AWS][2013] == 1
    assert panel.size(AWS, 2009) == 0


def test_the_market_growth_is_the_change_of_its_logarithm(panel: EntryPanel) -> None:
    assert panel.growth(2012) == pytest.approx(math.log(1.3))
    assert panel.growth(2009) is None


def test_the_birth_of_a_category_leaves_the_provider_out(panel: EntryPanel) -> None:
    assert panel.birth(K8S, AWS) == 2012
    assert panel.birth(K8S, GCP) == 2013
    assert math.isinf(panel.birth(LAKE, AWS))


def test_the_coverage_counts_the_entries_inside_the_window(panel: EntryPanel) -> None:
    coverage = {row.provider: row for row in panel.coverage()}

    assert coverage[AWS].events == 3
    assert coverage[AWS].share_years == 1
    assert coverage[AZURE].held == 1


def test_the_density_leaves_the_explained_catalogue_out(compounding_data: CompoundingData) -> None:
    density = CategoryDensity(compounding_data.categories, compounding_data.snapshot)

    with_aws = density.proximity(GCP)
    without_aws = density.proximity(AWS)

    assert with_aws[OBJECT, LAKE] > 0
    assert without_aws[OBJECT, LAKE] == 0
    assert numpy.allclose(without_aws, without_aws.T)
    held = numpy.array([True, False, False, False])
    assert 0 < density.density(AWS, held, K8S) <= 1


def test_the_foundation_share_and_experience_are_lagged(
    panel: EntryPanel, compounding_config: CompoundingConfig
) -> None:
    foundations = FoundationShare(panel, compounding_config.settings)
    sets = foundations.curated(compounding_config.foundation_sets())

    assert set(sets) == {K8S, LAKE}
    assert foundations.share(AWS, sets[K8S], 2013, 1) == 1.0
    assert foundations.share(AZURE, sets[K8S], 2011, 1) == 1.0
    assert foundations.experience(AWS, sets[K8S], 2013) == 3.0
    assert foundations.share(GCP, sets[K8S], 2012, 1) == 0.0


def test_the_data_driven_foundations_come_from_the_other_providers(
    panel: EntryPanel, compounding_config: CompoundingConfig
) -> None:
    foundations = FoundationShare(panel, compounding_config.settings)

    sets = foundations.data_driven(GCP)

    assert OBJECT in sets[K8S] or VM in sets[K8S]
    assert K8S not in sets.get(K8S, numpy.array([], dtype=numpy.intp))


def test_the_hazard_rows_are_at_risk_until_the_entry(
    panel: EntryPanel, compounding_data: CompoundingData, compounding_config: CompoundingConfig
) -> None:
    foundations = FoundationShare(panel, compounding_config.settings)
    builder = RiskSetBuilder(
        panel, CategoryDensity(compounding_data.categories, compounding_data.snapshot), foundations
    )
    sets = {AWS: foundations.curated(compounding_config.foundation_sets())}

    risk_set = builder.build(FitKind.HAZARD, [AWS], Specification.BASE, 1, sets)

    rows = {
        (int(column), int(year)): float(event)
        for column, year, event in zip(risk_set.columns, risk_set.years, risk_set.y, strict=True)
    }
    assert rows == {
        (K8S, 2011): 0.0,
        (K8S, 2012): 0.0,
        (K8S, 2013): 1.0,
        (LAKE, 2011): 0.0,
        (LAKE, 2012): 0.0,
        (LAKE, 2013): 0.0,
        (LAKE, 2014): 1.0,
    }
    assert risk_set.names == ["foundations", "experience", "size", "market", "age"]
    assert risk_set.events() == 2


def test_the_share_specification_drops_the_years_without_share(
    panel: EntryPanel, compounding_data: CompoundingData, compounding_config: CompoundingConfig
) -> None:
    foundations = FoundationShare(panel, compounding_config.settings)
    builder = RiskSetBuilder(
        panel, CategoryDensity(compounding_data.categories, compounding_data.snapshot), foundations
    )
    sets = {AWS: foundations.curated(compounding_config.foundation_sets())}

    risk_set = builder.build(FitKind.HAZARD, [AWS], Specification.SHARE, 1, sets)

    assert set(risk_set.years.tolist()) == {2013}
    assert risk_set.names[-1] == "share"


def test_a_pooled_risk_set_adds_provider_effects(
    panel: EntryPanel, compounding_data: CompoundingData, compounding_config: CompoundingConfig
) -> None:
    builder = RiskSetBuilder(
        panel,
        CategoryDensity(compounding_data.categories, compounding_data.snapshot),
        FoundationShare(panel, compounding_config.settings),
    )

    risk_set = builder.build(FitKind.ENTRY, [AWS, AZURE, GCP], Specification.BASE, 1, {})

    assert risk_set.names[-2:] == ["fe:microsoft-azure", "fe:google-cloud-platform"]
    assert set(risk_set.providers) == {AWS, AZURE, GCP}
