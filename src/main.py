from __future__ import annotations

# Standard Library Imports.
import asyncio
import os
from datetime import UTC, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import Final, List, Tuple

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from analytics.companies.companies_run import CompaniesRun
from analytics.companies.exception import CompaniesAnalyticsError
from analytics.markets.markets_collector import MarketsCollector
from analytics.metrics.metric_measurer import MetricMeasurer
from analytics.prices.price_collector import PriceCollector
from analytics.prices.prices_run import PricesRun
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from curated.bundle.settings_reader import SettingsReader
from curated.exception import CuratedError
from llm.exception import LLMError
from logger import setup_logging
from models.cloud.prices.settings.prices_settings import PricesSettings
from models.companies.enums import CompanyFeed
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.exception import MarketsModelError
from storage.engine.settings_reader import StorageSettingsReader
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
COMPANIES_VARIABLE: Final[str] = "COMPANIES"


async def crawl_catalogues(runner: CatalogueRunner, target: str, logger: Logger) -> None:
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
                logger.info("%d catalogues written to %s.", len(written), runner.storage.url)
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
    except CrawlerError, StorageError:
        logger.error("The following target is unavailable: %s", target)
    except Exception:
        logger.exception("The crawl of the target %s failed unexpectedly.", target)


async def crawl_marketplaces(runner: CatalogueRunner, target: str, logger: Logger) -> None:
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
                logger.info("%d marketplaces written to %s.", len(written), runner.storage.url)
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
    except CrawlerError, StorageError:
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
    except CrawlerError, StorageError:
        logger.error("The market statistics are unavailable.")
    except Exception:
        logger.exception("The market statistics crawl failed unexpectedly.")


async def collect_metrics(runner: CatalogueRunner, storage: Storage, logger: Logger) -> None:
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
            written += await storage.metrics.replace_source(source, measurer.measure(source, facts, now))
    except CrawlerError, StorageError:
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
        catalog = await storage.catalogs.markets()
        chronology = await storage.catalogs.chronology()
    except (MarketsModelError, ValueError) as e:
        logger.error("The markets crawl scope is invalid: %s", e)
        return
    except (CuratedError, StorageError) as e:
        logger.error("The markets catalogue is unavailable: %s", e)
        return
    collector = MarketsCollector(catalog, chronology, storage, logger)
    written = 0
    try:
        for feed in feeds:
            written += await runner.stream_markets(feed, collector.write, catalog, scope)
        written += await collector.finish(feeds)
    except CrawlerError, StorageError:
        logger.error("The markets data are unavailable.")
        return
    logger.info("Markets crawl over: %d rows written from %s.", written, ", ".join(feed.value for feed in feeds))


def company_feeds(target: str, logger: Logger) -> List[CompanyFeed]:
    """Read the companies sources of a run from `CRAWLER_TARGET`.

    Args:
        target (str): The target: empty or `all` for every source, else sources separated by commas.
        logger (Logger): The program logger.

    Returns:
        List[CompanyFeed]: The sources, in the order a full crawl runs them (the patent pages after the search).
    """
    names = {name.strip().casefold() for name in target.split(",") if name.strip()}
    every = [*CrawlerFactory.COMPANIES_MAP, *CompaniesRun.LOCAL_FEEDS]
    if not names or ALL_TARGETS in names:
        return [feed for feed in every if feed not in CompaniesRun.ON_DEMAND_FEEDS]
    unknown = sorted(names - {feed.value for feed in CompanyFeed})
    if unknown:
        expected = ", ".join(CompanyFeed)
        logger.warning("Unknown companies sources ignored: %s (expected %s).", ", ".join(unknown), expected)
    return [feed for feed in every if feed.value in names]


async def collect_companies(runner: CatalogueRunner, target: str, logger: Logger) -> None:
    """Crawl the financial statements, patents and papers of the chronology's companies, and derive their series.

    Args:
        runner (CatalogueRunner): The crawl runner (its storage is open).
        target (str): The `CRAWLER_TARGET`: the sources (`edgar-financials`, `gfinance-statements`,
            `google-patents`, `google-patents-pages`, `openalex`), every one by default.
        logger (Logger): The program logger.

    Notes:
        `COMPANIES` (e.g. `nvidia,tsmc`) limits the crawl to some companies. The patents search resumes from the
        stored windows, the patent pages read the next publications waiting (`CRAWLER_PATENT_PAGES` of them).
    """
    feeds = company_feeds(target, logger)
    try:
        scope = CrawlScope(companies=os.getenv(COMPANIES_VARIABLE, ""))
    except (MarketsModelError, ValueError) as e:
        logger.error("The companies crawl scope is invalid: %s", e)
        return
    try:
        written = await CompaniesRun(runner, logger).run(feeds, scope)
    except (CrawlerError, CuratedError, CompaniesAnalyticsError, StorageError) as e:
        logger.error("The companies data are unavailable: %s", e)
        return
    logger.info("Companies crawl over: %d rows written from %s.", written, ", ".join(feed.value for feed in feeds))


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
    logger.info("%d files imported (%d items) from %s.", len(imported), sum(imported.values()), folder)


def read_prices_settings(logger: Logger) -> PricesSettings:
    """Read the resource caps of the price crawl (the `prices` block of `conf/settings.yaml`).

    Args:
        logger (Logger): The program logger.

    Returns:
        PricesSettings: The settings, the defaults when the block cannot be read.
    """
    try:
        settings = PricesSettings.model_validate(SettingsReader(logger=logger).block("prices"))
    except (CuratedError, ValidationError) as e:
        logger.error("The prices settings cannot be read, the defaults are used: %s", e)
        return PricesSettings()
    logger.debug(
        "Prices settings read: %d ms between requests, merges up to %d s.",
        settings.request_delay_ms,
        settings.merge_timeout_s,
    )
    return settings


async def collect_prices(runner: CatalogueRunner, target: str, logger: Logger) -> None:
    """Crawl the prices and free offers of the target providers (or `all` of them), within the resource caps.

    Args:
        runner (CatalogueRunner): The crawl runner (its storage is open).
        target (str): The `CRAWLER_TARGET`: providers separated by commas, every one when empty or `all`.
        logger (Logger): The program logger.

    Notes:
        The resource caps are the `prices` block of `conf/settings.yaml`: run the command under a cgroup cap as
        well (`systemd-run --user --scope -p MemoryMax=1500M -p CPUQuota=150% ...`).
    """
    names = {name.strip().casefold() for name in target.split(",") if name.strip()}
    known = {provider.value: provider for provider in runner.factory.CRAWLER_MAP}
    if not names or ALL_TARGETS in names:
        providers = list(runner.factory.CRAWLER_MAP)
    else:
        unknown = sorted(names - set(known))
        if unknown:
            logger.warning("Unknown providers ignored: %s (known: %s).", ", ".join(unknown), ", ".join(sorted(known)))
        providers = [known[name] for name in sorted(names & set(known))]
    settings = read_prices_settings(logger)
    logger.info("Crawling the prices of %d providers.", len(providers))
    results = await PricesRun(runner, settings, logger).run(providers)
    changed = sum(closed + inserted for closed, inserted in results.values())
    if not results:
        logger.warning("No provider was crawled for its prices.")
    elif not changed:
        logger.info("No price changed in %d providers.", len(results))
    logger.info("Prices crawled: %d rows changed over %d providers.", changed, len(results))


async def report_price_coverage(runner: CatalogueRunner, target: str, logger: Logger) -> None:
    """Apply the curated price coverage of the target providers (or `all` of them), then report how it stands.

    Args:
        runner (CatalogueRunner): The crawl runner (its storage is open).
        target (str): The `CRAWLER_TARGET`: providers separated by commas, every one when empty or `all`.
        logger (Logger): The program logger.

    Notes:
        The curated coverage (`conf/prices/coverage/<provider>.yaml`) is applied first: its statements are merged
        and every price is linked again, the curated links first. A product is priced (a current price, free
        included), stated unpriced (on request, included in another
        service, or not public, with a reason) or missing. The exit gate of the price extraction is no missing
        product: each missing one is listed.
    """
    names = {name.strip().casefold() for name in target.split(",") if name.strip()}
    providers = [
        provider
        for provider in runner.factory.CRAWLER_MAP
        if not names or ALL_TARGETS in names or provider.value in names
    ]
    collector = PriceCollector(runner.storage, logger)
    totals = [0, 0, 0, 0]
    for provider in providers:
        await collector.curate(provider, runner.factory.CRAWLER_MAP[provider].name_prefixes)
        coverage = await runner.storage.prices.coverage(provider.value)
        priced = sum(1 for _, has_price, _ in coverage if has_price)
        unpriced = sum(1 for _, has_price, stated in coverage if stated and not has_price)
        missing = [name for name, has_price, stated in coverage if not has_price and not stated]
        for index, count in enumerate((len(coverage), priced, unpriced, len(missing))):
            totals[index] += count
        logger.info(
            "%s: %d live products, %d priced, %d stated unpriced, %d missing.",
            provider.value,
            len(coverage),
            priced,
            unpriced,
            len(missing),
        )
        if missing:
            logger.warning("%s products without price: %s", provider.value, "; ".join(missing))
    if totals[3]:
        logger.warning("The price coverage gate is open: %d of %d live products have no price.", totals[3], totals[0])
    else:
        logger.info("Every one of the %d live products is priced or stated unpriced.", totals[0])
    logger.info("Price coverage: %d live products, %d priced, %d stated unpriced, %d missing.", *totals)


async def run_source(source: CrawlSource, target: str, storage: Storage, logger: Logger) -> None:
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
        case CrawlSource.COMPANIES:
            await collect_companies(runner, target, logger)
        case CrawlSource.PRICES:
            await collect_prices(runner, target, logger)
        case CrawlSource.PRICE_COVERAGE:
            await report_price_coverage(runner, target, logger)
        case CrawlSource.LAUNCH_DATES:
            dated = await runner.date_launches()
            logger.info("%d catalogues dated, %d products changed.", len(dated), sum(dated.values()))
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
        the leaders of the chronology (`CRAWLER_TARGET` picks the sources). `CRAWLER_SOURCE=companies` crawls the
        financial statements, patents and research papers of the chronology's companies (`CRAWLER_TARGET` picks the
        sources, `COMPANIES` the companies). `CRAWLER_SOURCE=launch-dates` dates the stored catalogue products by their
        curated launch (`data/curated/launches.json`), without crawling. `CRAWLER_SOURCE=prices` crawls the prices of
        the `CRAWLER_TARGET` providers, `CRAWLER_SOURCE=price-coverage` reports which of their products have none.
        Everything is written to the PostgreSQL storage (`CRAWLER_DATABASE_URL`).
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
        storage_settings = StorageSettingsReader().read()
        if source in (CrawlSource.PRICES, CrawlSource.PRICE_COVERAGE):
            timeout = max(storage_settings.command_timeout_s, read_prices_settings(logger).merge_timeout_s)
            storage_settings = storage_settings.model_copy(update={"command_timeout_s": timeout})
            logger.info("The price statements may run %d s.", timeout)
        async with Storage(storage_settings) as storage:
            await run_source(source, target, storage, logger)
    except StorageError as e:
        logger.error("The storage is unavailable: %s", e)
    except LLMError as e:
        logger.error("The language model tasks stopped: %s", e)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
