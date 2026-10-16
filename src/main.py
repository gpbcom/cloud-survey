from __future__ import annotations

# Standard Library Imports.
import asyncio
import os
from logging import Logger, getLogger
from typing import Final, Tuple

# First Party Imports.
from catalogue.exception import CatalogueStoreError
from catalogue.store import CatalogueStore
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from logger import setup_logging

ALL_TARGETS: Final[str] = "all"
CATALOGUE_SOURCE: Final[str] = "catalogue"
MARKETPLACE_SOURCE: Final[str] = "marketplace"
BOTH_SOURCES: Final[str] = "both"
RECLASSIFY: Final[str] = "reclassify"
STATISTICS_SOURCE: Final[str] = "statistics"
SOURCES: Final[Tuple[str, ...]] = (CATALOGUE_SOURCE, MARKETPLACE_SOURCE, BOTH_SOURCES, RECLASSIFY, STATISTICS_SOURCE)


async def crawl_catalogues(runner: CatalogueRunner, target: str, logger: Logger) -> None:
    """Crawl the catalogue of a target (or `all` of them) into `output/<provider>.json`.

    Args:
        runner (CatalogueRunner): The crawl runner.
        target (str): The cloud provider, or `all`.
        logger (Logger): The program logger.
    """
    try:
        if target == ALL_TARGETS:
            written = await runner.run_all()
            if written:
                logger.info("%d catalogues written to %s.", len(written), runner.store.output_dir)
            else:
                logger.warning("No catalogue written (see the crawl errors above).")
        else:
            path = await runner.run(target)
            logger.info("The %s catalogue has been written to %s.", target, path)
    except EmptyCrawlError:
        logger.warning("No product fetched from target: %s (see the crawl errors above).", target)
    except CrawlerError, CatalogueStoreError:
        logger.error("The following target is unavailable: %s", target)
    except Exception:
        logger.exception("The crawl of the target %s failed unexpectedly.", target)


async def crawl_marketplaces(runner: CatalogueRunner, target: str, logger: Logger) -> None:
    """Crawl the marketplace of a target (or `all` of them) into `output/marketplaces/<provider>.json`.

    Args:
        runner (CatalogueRunner): The crawl runner.
        target (str): The cloud provider, or `all`.
        logger (Logger): The program logger.
    """
    try:
        if target == ALL_TARGETS:
            written = await runner.run_all_marketplaces()
            if written:
                logger.info("%d marketplaces written to %s.", len(written), runner.marketplace_store.output_dir)
            else:
                logger.warning("No marketplace written (see the crawl errors above).")
        else:
            path = await runner.run_marketplace(target)
            logger.info("The %s marketplace has been written to %s.", target, path)
    except EmptyCrawlError:
        logger.warning("No software fetched from the marketplace of: %s (see the crawl errors above).", target)
    except CrawlerError, CatalogueStoreError:
        logger.error("The marketplace of the following target is unavailable: %s", target)
    except Exception:
        logger.exception("The marketplace crawl of the target %s failed unexpectedly.", target)


async def crawl_statistics(runner: CatalogueRunner, logger: Logger) -> None:
    """Crawl the cloud market statistics (Synergy Research Group) into `output/stats/synergy.json`.

    Args:
        runner (CatalogueRunner): The crawl runner.
        logger (Logger): The program logger.
    """
    try:
        path = await runner.run_statistics()
        logger.info("The market statistics have been written to %s.", path)
    except EmptyCrawlError:
        logger.warning("No market statistics fetched (see the crawl errors above).")
    except CrawlerError, CatalogueStoreError:
        logger.error("The market statistics are unavailable.")
    except Exception:
        logger.exception("The market statistics crawl failed unexpectedly.")


async def main() -> None:
    """Program entrypoint: crawl the `CRAWLER_TARGET` catalogue and/or marketplace (`CRAWLER_SOURCE`).

    `CRAWLER_SOURCE=reclassify` crawls nothing: it classifies the stored marketplace software again with the current
    rules (`conf/classification.yaml`), whatever the target. `CRAWLER_SOURCE=statistics` crawls the cloud market
    statistics, whatever the target.
    """
    logger: Logger = getLogger(__name__)
    logger.info("Starting the crawler.")
    source = os.getenv("CRAWLER_SOURCE", CATALOGUE_SOURCE).strip().casefold() or CATALOGUE_SOURCE
    if source == RECLASSIFY:
        written = CatalogueRunner(store=CatalogueStore(), factory=CrawlerFactory()).reclassify_marketplaces()
        logger.info("%d marketplace files classified again.", len(written))
        return
    if source == STATISTICS_SOURCE:
        await crawl_statistics(CatalogueRunner(store=CatalogueStore(), factory=CrawlerFactory()), logger)
        return
    target = os.getenv("CRAWLER_TARGET", None)
    if not target:
        logger.error("No target defined.")
        return
    if source not in SOURCES:
        logger.error("Unknown crawl source %r: CRAWLER_SOURCE must be one of %s.", source, ", ".join(SOURCES))
        return
    logger.debug("Target read from CRAWLER_TARGET: %s (source %s)", target, source)
    runner = CatalogueRunner(store=CatalogueStore(), factory=CrawlerFactory())
    if source in (CATALOGUE_SOURCE, BOTH_SOURCES):
        await crawl_catalogues(runner, target, logger)
    if source in (MARKETPLACE_SOURCE, BOTH_SOURCES):
        await crawl_marketplaces(runner, target, logger)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
