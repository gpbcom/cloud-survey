from __future__ import annotations

from typing import Dict, List, Tuple

from pydantic import JsonValue
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.widgets.software_details import SoftwareDetails
from gui.product_model.product_row import ProductRow
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from gui.widgets.details.product_details import ProductDetails
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import ItemFilter
from models.taxonomy.enums import CategorySource, Language
from models.taxonomy.labels.source_label import SourceLabel


def software(**fields: JsonValue) -> MarketplaceSoftware:
    values: Dict[str, JsonValue] = {
        "name": "Postgres Pro",
        "description": "A database",
        "marketplace_categories": ["Базы данных"],
        "categories": [SoftwareCategory.DEVELOPER_TOOL.value],
        **fields,
    }
    return MarketplaceSoftware.model_validate(values)


def test_the_software_shows_its_categories_and_translated_labels(qapp: QApplication, qtbot: QtBot) -> None:
    cache = TaxonomyCache()
    cache._on_labels([SourceLabel(id=4, text="Базы данных", language=Language.RUSSIAN, name_en="Databases")])
    details = SoftwareDetails(Theme(), taxonomy=cache)
    listing = software(service_categories=["relational-database"], source_label_ids=[4], categories_source="user")
    details.show_row(SoftwareRow(CloudProvider.CLOUD_RU, listing, CRAWLED_AT))
    text = details.categories_label.text()

    assert "Databases &gt; Relational databases" in text
    assert "Databases (Базы данных)" in text
    assert "set by hand" in text
    emitted: List[Tuple[str, str]] = []
    details.filter_requested.connect(lambda name, value: emitted.append((name, value)))
    details._on_link(details.sheet.href(ItemFilter.SERVICE_CATEGORIES, "relational-database"))
    details._on_link(details.sheet.href(ItemFilter.SOURCE_LABELS, "4"))
    assert emitted == [("service-categories", "relational-database"), ("source-labels", "4")]


def test_an_item_filed_in_a_domain_only_shows_the_domain(qapp: QApplication) -> None:
    details = SoftwareDetails(Theme())

    details.show_row(SoftwareRow(CloudProvider.CIVO, software(service_domains=["data-analytics"]), CRAWLED_AT))

    assert "Data Platforms &amp; Analytics" in details.categories_label.text()
    text = details.categories_label.text()
    assert "Базы данных" in text, "the raw labels are shown while the names are not read"
    assert details.sheet.SCHEME + ":" + ItemFilter.SOURCE_LABELS.value not in text, "a raw label is not clickable"


def test_a_product_not_categorized_yet_says_so(qapp: QApplication) -> None:
    details = ProductDetails(Theme())
    product = CloudProduct(name="EC2", description="Servers", categories_source=CategorySource.RULES)

    details.show_row(ProductRow(CloudProvider.AWS, product, CRAWLED_AT))

    assert "Not categorized yet" in details.categories_label.text()
    assert "Not given by the catalogue" in details.categories_label.text()
