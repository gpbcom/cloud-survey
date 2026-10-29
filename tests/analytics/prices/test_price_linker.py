from __future__ import annotations

from typing import Dict, Optional, Tuple

from analytics.prices.price_linker import PriceLinker

PRODUCTS: Dict[int, Tuple[str, Optional[str]]] = {
    1: ("Amazon EC2", "https://aws.amazon.com/ec2/"),
    2: ("Elastic Compute Service (ECS)", None),
    3: ("Cloud Object Storage", "https://www.arubacloud.com/cloud-object-storage"),
    4: ("Managed Databases", None),
    5: ("Managed Kubernetes", None),
}


def test_a_service_named_as_a_product_is_linked_without_its_brand() -> None:
    links = PriceLinker().links(PRODUCTS, [("EC2", "https://pricing.aws/ec2.csv", "")], ["Amazon ", "AWS "])

    assert links == [("EC2", "https://pricing.aws/ec2.csv", "", 1)]


def test_parenthesized_notes_and_punctuation_are_ignored() -> None:
    links = PriceLinker().links(PRODUCTS, [("Elastic-Compute Service", "https://api", "")])

    assert links == [("Elastic-Compute Service", "https://api", "", 2)]


def test_a_price_read_from_a_product_page_is_linked_to_it() -> None:
    source = "https://arubacloud.com/cloud-object-storage/?lang=en"

    assert PriceLinker().links(PRODUCTS, [("Pay-per-use", source, "")]) == [("Pay-per-use", source, "", 3)]


def test_a_contained_name_links_only_when_it_matches_one_product() -> None:
    linker = PriceLinker()

    assert linker.links(PRODUCTS, [("Managed Databases for PostgreSQL", "x", "")]) == [
        ("Managed Databases for PostgreSQL", "x", "", 4)
    ]
    assert linker.links(PRODUCTS, [("Managed", "x", "")]) == []


def test_nothing_is_linked_without_products() -> None:
    assert PriceLinker().links({}, [("EC2", "x", "")]) == []


def test_a_curated_link_wins_over_the_automatic_matching() -> None:
    curated = {"Managed Kubernetes": [r"^publiccloud kube"], "Unknown product": ["x"]}

    links = PriceLinker().links(
        PRODUCTS, [("publiccloud kube standard", "x", ""), ("EC2", "x", "")], ["Amazon "], curated
    )

    assert links == [("publiccloud kube standard", "x", "", 5), ("EC2", "x", "", 1)]


def test_the_product_detail_is_matched_before_the_service_name() -> None:
    links = PriceLinker().links(PRODUCTS, [("Storage", "x", "Cloud Object Storage"), ("Amazon EC2", "x", "Nope")])

    assert links == [("Storage", "x", "Cloud Object Storage", 3), ("Amazon EC2", "x", "Nope", 1)]


def test_the_row_links_of_live_products_are_resolved() -> None:
    links = PriceLinker().row_links(PRODUCTS, {"Cloud Object Storage": ["archive", "cold"], "Gone": ["x"]})

    assert links == [("archive", 3), ("cold", 3)]


def test_the_curated_links_win_over_a_service_named_exactly_as_a_broad_product() -> None:
    curated = {"Managed Kubernetes": ["^managed databases$"]}

    links = PriceLinker().links(PRODUCTS, [("managed databases", "x", ""), ("Managed Databases", "y", "")], [], curated)

    assert links == [("managed databases", "x", "", 5), ("Managed Databases", "y", "", 5)]


def test_a_service_named_exactly_as_a_product_is_linked_to_it_without_curated_link() -> None:
    links = PriceLinker().links(PRODUCTS, [("managed databases", "x", "")], [], {"Managed Kubernetes": ["^k8s$"]})

    assert links == [("managed databases", "x", "", 4)]


def test_the_statements_named_exactly_as_a_product_are_matched_first() -> None:
    services = [
        ("Managed databases", "x#price-coverage", ""),
        ("EC2", "x#price-coverage", ""),
        ("Managed databases", "y", ""),
    ]

    assert PriceLinker().exact_links(PRODUCTS, services, "#price-coverage") == [
        ("Managed databases", "x#price-coverage", "", 4)
    ]


def test_a_product_on_a_section_of_a_shared_page_does_not_claim_that_page() -> None:
    products = {1: ("Object Store", "https://www.civo.com/pricing#object-store"), 2: ("Civo Compute", None)}

    links = PriceLinker().links(products, [("Compute Instances", "https://www.civo.com/pricing", "")])

    assert links == []
