from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import (
    CatalogueFormatError,
    CrawlerError,
    EmptyCatalogueError,
    EmptyCrawlError,
    ParseNotImplementedError,
    UnknownCrawlerTargetError,
)
from crawler.factory import CrawlerFactory


class TestCrawlerError:
    def test_is_an_exception(self) -> None:
        assert issubclass(CrawlerError, Exception)

    def test_keeps_its_message(self) -> None:
        error = CrawlerError("Something went wrong.")

        assert error.message == "Something went wrong."
        assert str(error) == "Something went wrong."


class TestUnknownCrawlerTargetError:
    def test_hierarchy(self) -> None:
        assert issubclass(UnknownCrawlerTargetError, CrawlerError)
        assert issubclass(UnknownCrawlerTargetError, ValueError)

    def test_attributes_and_message(self) -> None:
        error = UnknownCrawlerTargetError("unknown-cloud")

        assert error.target == "unknown-cloud"
        assert str(error) == "Failed to identify suitable crawler for target: 'unknown-cloud'."

    def test_raised_by_the_factory(self) -> None:
        with pytest.raises(UnknownCrawlerTargetError) as exc_info:
            CrawlerFactory(logger=MagicMock()).get("unknown-cloud")

        assert exc_info.value.target == "unknown-cloud"
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestParseNotImplementedError:
    def test_hierarchy(self) -> None:
        assert issubclass(ParseNotImplementedError, CrawlerError)
        assert issubclass(ParseNotImplementedError, NotImplementedError)

    def test_attributes_and_message(self) -> None:
        error = ParseNotImplementedError("AWSCrawler")

        assert error.crawler == "AWSCrawler"
        assert str(error) == "AWSCrawler: the `parse` methods will be implemented in children classes."

    def test_raised_by_crawlers_without_extraction(self) -> None:
        class DraftCrawler(BaseCloudCrawler):
            """Crawler not implementing the extraction yet."""

        with pytest.raises(ParseNotImplementedError) as exc_info:
            DraftCrawler().extract_products(MagicMock())

        assert exc_info.value.crawler == "DraftCrawler"


class TestCatalogueFormatError:
    def test_hierarchy(self) -> None:
        assert issubclass(CatalogueFormatError, CrawlerError)

    def test_attributes_and_message(self) -> None:
        error = CatalogueFormatError("aws", "https://aws.amazon.com/api", "`items` is not a list")

        assert (error.crawler, error.url, error.reason) == (
            "aws",
            "https://aws.amazon.com/api",
            "`items` is not a list",
        )
        assert str(error) == "aws: unexpected catalogue format at https://aws.amazon.com/api: `items` is not a list."


class TestEmptyCatalogueError:
    def test_hierarchy(self) -> None:
        assert issubclass(EmptyCatalogueError, CrawlerError)

    def test_attributes_and_message(self) -> None:
        error = EmptyCatalogueError("azure", "https://azure.microsoft.com/en-us/products/")

        assert (error.crawler, error.url) == ("azure", "https://azure.microsoft.com/en-us/products/")
        assert str(error) == "azure: no product found at https://azure.microsoft.com/en-us/products/."


class TestEmptyCrawlError:
    def test_hierarchy(self) -> None:
        assert issubclass(EmptyCrawlError, CrawlerError)

    def test_attributes_and_message(self) -> None:
        error = EmptyCrawlError("scaleway")

        assert error.provider == "scaleway"
        assert str(error) == "The scaleway crawl produced no product: its catalogue file is left unchanged."
