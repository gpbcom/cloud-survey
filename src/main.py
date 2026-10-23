from __future__ import annotations

# Standard Library Imports.
import asyncio
import os
from datetime import UTC, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import Final, List, Tuple

# First Party Imports.
from analytics.markets.markets_collector import MarketsCollector
from analytics.metrics.metric_measurer import MetricMeasurer  # noqa: E501
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from crawler.markets.catalog_loader import MarketsCatalogLoader
from crawler.runner import CatalogueRunner
from llm.exception import LLMError
from logger import setup_logging
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.exception import MarketsModelError
from storage.exception import StorageError
from storage.importer.json_importer import JsonImporter
from storage.storage import Storage

ALL_TARGETS: Final[str] = "all"
SOURCES: Final[Tuple[str, ...]] = tuple(CrawlSource)
IMPORT_DIR_VARIABLE: Final[str] = "CRAWLER_IMPORT_DIR"
IMPORT_REPLACE_VARIABLE: Final[str] = "CRAWLER_IMPORT_REPLACE"
DEFAULT_IMPORT_DIR: Final[str] = "output"
MARKETS_AREAS_VARIABLE: Final[str] = "MARKETS_AREAS"
MARKETS_LISTINGS_VARIABLE: Final[str] = "MARKETS_LISTINGS"
MARKETS_SINCE_VARIABLE: Final[str] = "MARKETS_SINCE"


async def crawl_catalogues(runner: CatalogueRunner, target: str, logger: Logger) -> None: # noqa: E501
    """Crawl the catalogue of a target (or `all` of them) into the storage.

    Args:
        runner (CatalogueRunner): The crawl runner.
        target (str): The cloud provider, or `all`.
        logger (Logger): The program logger.
    """
    try:
        if target == ALL_TARGETS:
            written = await runner.run_all()
            if written:
                logger.info("%d catalogues written to %s.", len(written), runner.storage.url)   # noqa: E501
            else:
                logger.warning("No catalogue written (see the crawl errors above).")
        else:
            summary = await runner.run(target)
            logger.info(
                "The %s catalogue has been written (crawl %d: %d products, %d added, %d updated, %d deleted).",
                target,
                summary.crawl_id,
                summary.found,
                summary.added,
                summary.updated,
                summary.deleted,
            )
    except EmptyCrawlError:
        logger.warning("No product fetched from target: %s (see the crawl errors above).", target)
    except (CrawlerError, StorageError):
        logger.error("The following target is unavailable: %s", target)
    except Exception:
        logger.exception("The crawl of the target %s failed unexpectedly.", target)  # noqa: E501


async def crawl_marketplaces(runner: CatalogueRunner, target: str, logger: Logger) -> None:   # noqa: E501
    """Crawl the marketplace of a target (or `all` of them) into the storage.

    Args:
        runner (CatalogueRunner): The crawl runner.
        target (str): The cloud provider, or `all`.
        logger (Logger): The program logger.
    """
    try:
        if target == ALL_TARGETS:
            written = await runner.run_all_marketplaces()
            if written:
                logger.info("%d marketplaces written to %s.", len(written), runner.storage.url)   # noqa: E501
            else:
                logger.warning("No marketplace written (see the crawl errors above).")
        else:
            summary = await runner.run_marketplace(target)
            logger.info(
                "The %s marketplace has been written (crawl %d: %d software, %d added, %d updated, %d deleted).",
                target,
                summary.crawl_id,
                summary.found,
                summary.added,
                summary.updated,
                summary.deleted,
            )
    except EmptyCrawlError:
        logger.warning("No software fetched from the marketplace of: %s (see the crawl errors above).", target)
    except (CrawlerError, StorageError):
        logger.error("The marketplace of the following target is unavailable: %s", target)
    except Exception:
        logger.exception("The marketplace crawl of the target %s failed unexpectedly.", target)


async def crawl_statistics(runner: CatalogueRunner, logger: Logger) -> None:
    """Crawl the cloud market statistics (Synergy Research Group) into the storage.

    Args:
        runner (CatalogueRunner): The crawl runner.
        logger (Logger): The program logger.
    """
    try:
        summary = await runner.run_statistics()
        logger.info("The market statistics have been written (crawl %d: %d reports).", summary.crawl_id, summary.found)
    except EmptyCrawlError:
        logger.warning("No market statistics fetched (see the crawl errors above).")
    except (CrawlerError, StorageError):
        logger.error("The market statistics are unavailable.")
    except Exception:
        logger.exception("The market statistics crawl failed unexpectedly.")


async def collect_metrics(runner: CatalogueRunner, storage: Storage, logger: Logger) -> None:  # noqa: E501
    """Compute the provider metrics from the stored datasets, then crawl and measure the metric sources.

    Args:
        runner (CatalogueRunner): The crawl runner.
        storage (Storage): The open storage.
        logger (Logger): The program logger.
    """
    now = datetime.now(UTC)
    try:
        written = await storage.refresh_metrics(now)
        measurer = MetricMeasurer(logger)
        for source, facts in (await runner.crawl_metrics()).items():
            written += await storage.metrics.replace_source(source, measurer.measure(source, facts, now))  # noqa: E501
    except (CrawlerError, StorageError):
        logger.error("The provider metrics are unavailable.")
        return
    logger.info("%d provider metrics computed again.", written)


def market_feeds(target: str, logger: Logger) -> List[MarketFeed]:
    """Read the markets sources of a run from `CRAWLER_TARGET`.

    Args:
        target (str): The target: empty or `all` for every source, else sources separated by commas.
        logger (Logger): The program logger.

    Returns:
        List[MarketFeed]: The sources, in the order a full crawl runs them (the World Bank weights join StatCounter,
            the union estimates need them).
    """
    names = {name.strip().casefold() for name in target.split(",") if name.strip()}
    if not names or ALL_TARGETS in names:
        return list(CrawlerFactory.MARKETS_MAP)
    unknown = sorted(names - {feed.value for feed in MarketFeed})
    if unknown:
        logger.warning("Unknown markets sources ignored: %s (expected %s).", ", ".join(unknown), ", ".join(MarketFeed))
    if MarketFeed.STATCOUNTER in names:
        names.add(MarketFeed.WORLD_BANK)
    return [feed for feed in CrawlerFactory.MARKETS_MAP if feed.value in names]


async def collect_markets(runner: CatalogueRunner, storage: Storage, target: str, logger: Logger) -> None:
    """Crawl the market shares, stock prices and exchange rates, measure them and write them.

    Args:
        runner (CatalogueRunner): The crawl runner.
        storage (Storage): The open storage.
        target (str): The `CRAWLER_TARGET`: the sources (`statcounter`, `google-finance`, `fred`, `worldbank`),
            every one by default.
        logger (Logger): The program logger.

    Notes:
        `MARKETS_AREAS` (e.g. `ww,US,GB`) and `MARKETS_LISTINGS` (e.g. `NYSE:IBM`) limit the crawl, and
        `MARKETS_SINCE` (`YYYY-MM`) reads only the months from then: the way to keep the series up to date.
    """
    feeds = market_feeds(target, logger)
    try:
        scope = CrawlScope(
            areas=os.getenv(MARKETS_AREAS_VARIABLE, ""),
            listings=os.getenv(MARKETS_LISTINGS_VARIABLE, ""),
            since=os.getenv(MARKETS_SINCE_VARIABLE, ""),
        )
        catalog = MarketsCatalogLoader(logger).load()
        chronology = MarketsCatalogLoader(logger).chronology()
    except (MarketsModelError, ValueError) as e:
        logger.error("The markets crawl scope is invalid: %s", e)
        return
    except CrawlerError:
        logger.error("The markets catalogue is unavailable.")
        return
    collector = MarketsCollector(catalog, chronology, storage, logger)
    written = 0
    try:
        for feed in feeds:
            written += await runner.stream_markets(feed, collector.write, catalog, scope)
        written += await collector.finish(feeds)
    except (CrawlerError, StorageError):
        logger.error("The markets data are unavailable.")
        return
    logger.info("Markets crawl over: %d rows written from %s.", written, ", ".join(feed.value for feed in feeds))


async def import_json(storage: Storage, logger: Logger) -> None:
    """Import the JSON files of the former file storage (`CRAWLER_IMPORT_DIR`, `output/` by default).

    Args:
        storage (Storage): The open storage.
        logger (Logger): The program logger.
    """
    folder = Path(os.getenv(IMPORT_DIR_VARIABLE, DEFAULT_IMPORT_DIR).strip() or DEFAULT_IMPORT_DIR)
    replace = os.getenv(IMPORT_REPLACE_VARIABLE, "").strip().casefold() in ("1", "true", "yes", "on")
    if not folder.is_dir():
        logger.error("The folder %s to import does not exist.", folder)
        return
    imported = await JsonImporter(storage).import_folder(folder, replace)
    logger.info("%d files imported (%d items) from %s.", len(imported), sum(imported.values()), folder)  # noqa: E501


async def run_source(source: CrawlSource, target: str, storage: Storage, logger: Logger) -> None:  # noqa: E501
    """Run a crawl source (or the import, or the reclassification) on the open storage.

    Args:
        source (CrawlSource): The `CRAWLER_SOURCE`.
        target (str): The `CRAWLER_TARGET` of the crawls of catalogues and marketplaces, ignored otherwise.
        storage (Storage): The open storage.
        logger (Logger): The program logger.
    """
    runner = CatalogueRunner(storage=storage, factory=CrawlerFactory())
    match source:
        case CrawlSource.IMPORT_JSON:
            await import_json(storage, logger)
        case CrawlSource.RECLASSIFY:
            await runner.refresh_taxonomy()
            changed = await runner.reclassify_marketplaces()
            logger.info("%d marketplaces classified again, %d software changed.", len(changed), sum(changed.values()))
            products = await runner.reclassify_catalogues()
            logger.info("%d catalogues classified again, %d products changed.", len(products), sum(products.values()))
            logger.info("Run `VACUUM (ANALYZE) software, products` once a large reclassification is over.")
        case CrawlSource.TRANSLATE:
            translated, classified = await runner.translate()
            logger.info("%d labels translated, %d items categorized by the language model.", translated, classified)
            matched = await runner.correspond()
            logger.info("%d services matched with their equivalents by the language model.", matched)
        case CrawlSource.METRICS:
            await collect_metrics(runner, storage, logger)
        case CrawlSource.MARKETS:
            await collect_markets(runner, storage, target, logger)
        case CrawlSource.CORRESPOND:
            matched = await runner.correspond()
            logger.info("%d services matched with their equivalents by the language model.", matched)
        case CrawlSource.STATISTICS:
            await crawl_statistics(runner, logger)
        case CrawlSource.CATALOGUE | CrawlSource.MARKETPLACE | CrawlSource.BOTH:
            logger.debug("Target read from CRAWLER_TARGET: %s (source %s)", target, source.value)
            if source in (CrawlSource.CATALOGUE, CrawlSource.BOTH):
                await crawl_catalogues(runner, target, logger)
            if source in (CrawlSource.MARKETPLACE, CrawlSource.BOTH):
                await crawl_marketplaces(runner, target, logger)


async def main() -> None:
    """Program entrypoint: crawl the `CRAWLER_TARGET` catalogue and/or marketplace (`CRAWLER_SOURCE`).

    Notes:
        `CRAWLER_SOURCE=reclassify` crawls nothing: it applies the taxonomy seed (`conf/taxonomy/`), links the source
        labels again with the current rules (`conf/classification.yaml`), then categorizes the stored marketplace
        software and catalogue products again, whatever the target. `CRAWLER_SOURCE=statistics`
        crawls the cloud market statistics, whatever the target. `CRAWLER_SOURCE=import-json` imports the JSON files of
        the former file storage (`CRAWLER_IMPORT_DIR`, `CRAWLER_IMPORT_REPLACE`). `CRAWLER_SOURCE=translate` runs the
        language model tasks (labels, items, then equivalent services), `CRAWLER_SOURCE=correspond` matches the
        equivalent services only, `CRAWLER_SOURCE=metrics` computes the measures of the providers (the criteria of the
        driver analysis) again, `CRAWLER_SOURCE=markets` crawls the market shares, stock prices and exchange rates of
        the leaders of the chronology (`CRAWLER_TARGET` picks the sources). Everything is written to the
        PostgreSQL storage (`CRAWLER_DATABASE_URL`).
    """
    logger: Logger = getLogger(__name__)
    logger.info("Starting the crawler.")
    raw = os.getenv("CRAWLER_SOURCE", CrawlSource.CATALOGUE).strip().casefold() or CrawlSource.CATALOGUE
    if raw not in SOURCES:
        logger.error("Unknown crawl source %r: CRAWLER_SOURCE must be one of %s.", raw, ", ".join(SOURCES))
        return
    source = CrawlSource(raw)
    target = os.getenv("CRAWLER_TARGET", "") or ""
    if not target and source in (CrawlSource.CATALOGUE, CrawlSource.MARKETPLACE, CrawlSource.BOTH):
        logger.error("No target defined.")
        return
    try:
        async with Storage() as storage:
            await run_source(source, target, storage, logger)
    except StorageError as e:
        logger.error("The storage is unavailable: %s", e)
    except LLMError as e:
        logger.error("The language model tasks stopped: %s", e)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
