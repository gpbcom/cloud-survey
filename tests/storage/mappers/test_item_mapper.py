from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import Table

from models.cloud.enums import DateCaveat, DateSource, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from storage.mappers.item_mapper import ItemMapper
from storage.tables.base import Base
from storage.tables.items.software_row import SoftwareRow
from storage.tables.items.software_version_row import SoftwareVersionRow


def mapper() -> ItemMapper[MarketplaceSoftware]:
    tables = Base.metadata.tables
    software: Table = tables[SoftwareRow.__tablename__]
    return ItemMapper[MarketplaceSoftware](MarketplaceSoftware, software, tables[SoftwareVersionRow.__tablename__])


def test_an_item_is_stored_as_its_row_and_read_back(make_software: Callable[..., MarketplaceSoftware]) -> None:
    software = make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])
    item = MarketplaceSoftware.model_validate(
        {
            **software.model_dump(),
            "added_at": datetime(2026, 1, 1, tzinfo=UTC),
            "added_from": DateSource.WEBSITE,
            "added_caveat": DateCaveat.YEAR_ONLY,
            "marketplace_category_paths": [{"path": ["Data", "Databases"], "id": "db"}],
        }
    )

    row = mapper().to_row(item, "civo")

    assert (row["provider"], row["added_from"], row["added_caveat"], row["delivery"]) == (
        "civo",
        "website",
        "year-only",
        "saas",
    )
    assert row["marketplace_category_paths"] == [{"path": ["Data", "Databases"], "id": "db"}]
    assert row["fingerprint"] == item.fingerprint_hash()
    assert len(row["match_hash"]) == len(row["name_hash"]) == ItemMapper.HASH_SIZE  # type: ignore[arg-type]
    assert mapper().to_model(row) == item  # type: ignore[arg-type]
    assert not mapper().differs(row, row)  # type: ignore[arg-type]
    assert mapper().differs({**row, "name": "Other"}, row)  # type: ignore[arg-type]
    assert mapper().state_of(row) == item.state()  # type: ignore[arg-type]


def test_the_hashes_follow_the_match_keys(make_software: Callable[..., MarketplaceSoftware]) -> None:
    item = make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])

    match_hash, name_hash = mapper().key_hashes(item)

    assert match_hash == mapper().hash_key(item.match_keys()[0])
    assert name_hash == mapper().hash_key(item.match_keys()[-1])
    assert match_hash != name_hash
