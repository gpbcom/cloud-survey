from __future__ import annotations

from enum import StrEnum

import pytest

from models.cloud.enums import PROVIDER_COUNTRIES, CloudProvider, Country, PricingPolicy


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (CloudProvider.AWS, "amazon-web-services"),
        (CloudProvider.AZURE, "microsoft-azure"),
        (CloudProvider.GCP, "google-cloud-platform"),
        (CloudProvider.OVH, "ovh-cloud"),
        (CloudProvider.SCALEWAY, "scaleway"),
    ],
)
def test_cloud_provider_values(member: CloudProvider, value: str) -> None:
    assert member.value == value
    assert member == value
    assert CloudProvider(value) is member


def test_cloud_provider_members() -> None:
    assert len(CloudProvider) == 28
    assert {"AWS", "AZURE", "GCP", "OVH", "SCALEWAY", "IBM", "ORACLE", "ALIBABA", "ECLOUD"} <= {
        member.name for member in CloudProvider
    }


@pytest.mark.parametrize(
    ("member", "country"),
    [
        (CloudProvider.AWS, Country.UNITED_STATES),
        (CloudProvider.ORACLE, Country.UNITED_STATES),
        (CloudProvider.OVH, Country.FRANCE),
        (CloudProvider.SCALEWAY, Country.FRANCE),
        (CloudProvider.PROXIMUS, Country.BELGIUM),
        (CloudProvider.STACKIT, Country.GERMANY),
        (CloudProvider.SEEWEB, Country.ITALY),
        (CloudProvider.DEEP, Country.LUXEMBOURG),
        (CloudProvider.GIGAS, Country.SPAIN),
        (CloudProvider.INFOMANIAK, Country.SWITZERLAND),
        (CloudProvider.KRYSTAL, Country.UNITED_KINGDOM),
        (CloudProvider.ECLOUD, Country.CHINA),
    ],
)
def test_cloud_provider_countries(member: CloudProvider, country: Country) -> None:
    assert member.country is country


def test_every_cloud_provider_has_a_country() -> None:
    assert set(PROVIDER_COUNTRIES) == set(CloudProvider)


def test_every_country_has_two_providers_at_least() -> None:
    for country in Country:
        assert sum(provider.country is country for provider in CloudProvider) >= 2, country


def test_providers_are_grouped_by_country() -> None:
    countries = [provider.country for provider in CloudProvider]

    assert countries == sorted(countries, key=countries.index)
    assert list(dict.fromkeys(countries)) == list(Country)


@pytest.mark.parametrize(
    ("member", "value"),
    [(Country.UNITED_STATES, "us"), (Country.UNITED_KINGDOM, "gb"), (Country.SWITZERLAND, "ch"), (Country.CHINA, "cn")],
)
def test_country_values_are_iso_codes(member: Country, value: str) -> None:
    assert Country(value) is member


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (PricingPolicy.BY_ARTIFACT, "artifacts-billing"),
        (PricingPolicy.BY_RESOURCE, "resources-billing"),
    ],
)
def test_pricing_policy_values(member: PricingPolicy, value: str) -> None:
    assert member.value == value
    assert member == value
    assert PricingPolicy(value) is member


def test_pricing_policy_members() -> None:
    assert {member.name for member in PricingPolicy} == {"BY_ARTIFACT", "BY_RESOURCE"}


@pytest.mark.parametrize("enum_cls", [CloudProvider, Country, PricingPolicy])
def test_enums_are_str_enums(enum_cls: type[StrEnum]) -> None:
    for member in enum_cls:
        assert isinstance(member, str)
        assert str(member) == member.value


@pytest.mark.parametrize("enum_cls", [CloudProvider, Country, PricingPolicy])
def test_enum_values_are_unique(enum_cls: type[StrEnum]) -> None:
    values = [member.value for member in enum_cls]
    assert len(values) == len(set(values))


@pytest.mark.parametrize(("enum_cls", "value"), [(CloudProvider, "unknown-cloud"), (PricingPolicy, "flat-fee")])
def test_unknown_value_is_rejected(enum_cls: type[StrEnum], value: str) -> None:
    with pytest.raises(ValueError, match="is not a valid"):
        enum_cls(value)
