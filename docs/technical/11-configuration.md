[↑ Docs index](../README.md) · Technical

# 11 — Entry points and configuration

This chapter is the reference for how poc-crawler is started and configured:
- the console scripts and the real crawler entry point;
- how [`src/main.py`](../../src/main.py) dispatches each `CRAWLER_SOURCE`;
- every environment variable the code reads;
- every YAML file under [`src/conf/`](../../src/conf);
- the VS Code launch configurations.

## Contents

- [Entry points](#entry-points)
- [Source dispatch in main.py](#source-dispatch-in-mainpy)
- [Error handling of a run](#error-handling-of-a-run)
- [Environment variables](#environment-variables)
- [Configuration files](#configuration-files)
- [llm.yaml](#llmyaml)
- [logger.yaml](#loggeryaml)
- [classification.yaml and the taxonomy seed](#classificationyaml-and-the-taxonomy-seed)
- [Metrics configuration](#metrics-configuration)
- [VS Code launch configurations](#vs-code-launch-configurations)
- [See also](#see-also)

## Entry points

| Command | Target | What it does |
|---|---|---|
| `uv run python src/main.py` | [`main.main()`](../../src/main.py#L192) | **The crawler.** One run per `CRAWLER_SOURCE` (see below). |
| `uv run python -m gui.window.app`, or `poc-crawler-gui` | [`gui.window.app:main`](../../src/gui/window/app.py#L33) | The PyQt6 explorer. |
| `uv run install-stack` | [`scripts.install_stack:main`](../../scripts/install_stack.py#L254) | Starts PostgreSQL (Compose), applies the migrations, optionally imports the JSON files. |
| `uv run migrate-db …` | [`scripts.migrate_database:main`](../../scripts/migrate_database.py#L311) | Alembic commands and the taxonomy seed. |
| `poc-crawler` | [`crawler:main`](../../src/crawler/__init__.py) | **A stub.** It prints "Hello from poc-crawler!" and does not crawl. Use `python src/main.py`. |

In `__main__`, [`src/main.py`](../../src/main.py) calls [`setup_logging()`](../../src/logger/__init__.py#L50) and then `asyncio.run(main())`.

## Source dispatch in main.py

[`main()`](../../src/main.py#L192):
1. reads `CRAWLER_SOURCE` (casefolded, default `catalogue`) and checks it against [`CrawlSource`](../../src/crawler/enums.py);
2. reads `CRAWLER_TARGET`, which is required for `catalogue`, `marketplace` and `both` only;
3. opens `async with Storage()` and calls [`run_source()`](../../src/main.py#L152). That function builds a [`CatalogueRunner`](../../src/crawler/runner.py#L49) with a [`CrawlerFactory`](../../src/crawler/factory.py#L83) and dispatches with `match`/`case`.

```mermaid
flowchart TD
    start(["python src/main.py"]) --> src{"CRAWLER_SOURCE"}
    src -- "unknown" --> err1["ERROR log, exit"]
    src -- "catalogue / marketplace / both" --> tgt{"CRAWLER_TARGET set?"}
    tgt -- no --> err2["ERROR 'No target defined.'"]
    tgt -- "all" --> all["run_all / run_all_marketplaces<br/>parallel, CRAWLER_CONCURRENCY"]
    tgt -- "provider" --> one["run(target) / run_marketplace(target)"]
    src -- statistics --> st["crawl_statistics: run_statistics('synergy')"]
    src -- reclassify --> rc["refresh_taxonomy, reclassify_marketplaces, reclassify_catalogues"]
    src -- "import-json" --> ij["JsonImporter.import_folder(CRAWLER_IMPORT_DIR)"]
    src -- translate --> tr["translate(): LabelTranslator + ItemClassifier<br/>then correspond()"]
    src -- correspond --> co["correspond(): ServiceMatcher"]
    src -- metrics --> me["collect_metrics: refresh_metrics + crawl_metrics"]
    all --> after["_after_crawl per provider<br/>(LLM tasks if configured)"]
    one --> after
```

| `CRAWLER_SOURCE` | Needs a target | Call chain | Chapter |
|---|---|---|---|
| `catalogue` (default) | yes | [`crawl_catalogues`](../../src/main.py#L30) → [`run`](../../src/crawler/runner.py#L370) or [`run_all`](../../src/crawler/runner.py#L399) | [12](12-crawler-framework.md), [13](13-storage.md) |
| `marketplace` | yes | [`crawl_marketplaces`](../../src/main.py#L64) → [`run_marketplace`](../../src/crawler/runner.py#L442) or [`run_all_marketplaces`](../../src/crawler/runner.py#L474) | [12](12-crawler-framework.md) |
| `both` | yes | catalogues, then marketplaces | — |
| `statistics` | no | [`crawl_statistics`](../../src/main.py#L98) → [`run_statistics`](../../src/crawler/runner.py#L550) | [17](17-statistics-crawler.md) |
| `reclassify` | no | [`refresh_taxonomy`](../../src/crawler/runner.py#L496), [`reclassify_marketplaces`](../../src/crawler/runner.py#L512), [`reclassify_catalogues`](../../src/crawler/runner.py#L531) | [14](14-classification-engine.md) |
| `import-json` | no | [`import_json`](../../src/main.py#L136) → [`JsonImporter`](../../src/storage/importer/json_importer.py) | [13](13-storage.md) |
| `translate` | no | [`translate`](../../src/crawler/runner.py#L616), then [`correspond`](../../src/crawler/runner.py#L633) | [15](15-llm-layer.md) |
| `correspond` | no | [`correspond`](../../src/crawler/runner.py#L633) → `ServiceMatcher.run()` | [15](15-llm-layer.md) |
| `metrics` | no | [`collect_metrics`](../../src/main.py#L116) → `storage.refresh_metrics` → [`crawl_metrics`](../../src/crawler/runner.py#L585) → `MetricMeasurer` | [16](16-analytics.md) |

After a large `reclassify`, `run_source` logs a reminder to run `VACUUM (ANALYZE) software, products`.

## Error handling of a run

| Where | Caught | Outcome |
|---|---|---|
| `crawl_catalogues`, `crawl_marketplaces`, `crawl_statistics` | `EmptyCrawlError` | warning: nothing was crawled, so the stored dataset is kept |
| same | `CrawlerError`, `StorageError` | error logged |
| same | any other `Exception` | `logger.exception(... failed unexpectedly)` |
| [`_guarded`](../../src/crawler/runner.py#L155) (one provider of a parallel run) | the per-provider errors | logged, and the other providers go on |
| [`_after_crawl`](../../src/crawler/runner.py#L305) | `LLMError`, `StorageError` | warning: the crawl itself still succeeds |
| `main` | `StorageError`, `LLMError` | "The storage is unavailable" or "The language model tasks stopped" |

## Environment variables

| Variable | Default | Read by | Effect |
|---|---|---|---|
| `CRAWLER_SOURCE` | `catalogue` | [`main.py`](../../src/main.py#L208) | What the run does (table above). |
| `CRAWLER_TARGET` | — | [`main.py`](../../src/main.py#L213) | A `CloudProvider` value (e.g. `scaleway`, `amazon-web-services`) or `all`. |
| `CRAWLER_CONCURRENCY` | 4 | [`CatalogueRunner.__init__`](../../src/crawler/runner.py#L79) | Providers crawled at the same time. Invalid values are logged and replaced by the default. A warning is logged if it exceeds the pool. |
| `CRAWLER_IMPORT_DIR` | `output` | [`import_json`](../../src/main.py#L136) | Folder of the legacy JSON files. |
| `CRAWLER_IMPORT_REPLACE` | off | same | `1`/`true`/`yes`/`on` replaces the stored datasets. |
| `CRAWLER_DATABASE_URL` | `postgresql+asyncpg://crawler:crawler@localhost:5432/poc_crawler` | [`StorageSettingsReader`](../../src/storage/engine/settings_reader.py) | Database URL (asyncpg driver). |
| `CRAWLER_DATABASE_POOL_SIZE` | 5 (1–100) | same | Connections kept open. |
| `CRAWLER_DATABASE_MAX_OVERFLOW` | 30 (0–500) | same | Extra connections under load. Each running crawl holds one connection. |
| `CRAWLER_DATABASE_BATCH_SIZE` | 2000 (1–50,000) | same | Items per write batch of a crawl. |
| `CRAWLER_DATABASE_ECHO` | off | same | Logs every SQL statement. |
| `CRAWLER_LLM_CONFIG` | `src/conf/llm.yaml` | [`LLMSettingsLoader`](../../src/llm/settings_loader.py#L19) | Another LLM settings file. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | unset | [`LLMConfiguration`](../../src/models/configuration/llm/model/llm_configuration.py#L15) | **Named** in `llm.yaml` (`api_key`). When unset, no model is called. |
| `CRAWLER_SEC_USER_AGENT` | unset | [`BaseMetricsCrawler`](../../src/crawler/metrics/base.py#L32) via [`collectors.yaml`](../../src/conf/metrics/collectors.yaml) | User agent naming a contact, required by SEC EDGAR. |
| `GITHUB_TOKEN` | unset | same | GitHub API token (60 requests per hour without it). |
| `PEERINGDB_API_KEY` | unset | same | PeeringDB `Api-Key` header (anonymous queries are throttled). |
| `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `SSL_CERT_FILE` | unset | [`CaBundle`](../../src/crawler/tls/ca_bundle.py#L17) | Extra CA bundles merged with certifi's (e.g. a company proxy). |
| `POC_CRAWLER_CA_BUNDLES` | set by the code | same | Remembers the original bundles once `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` point at the merged file. |
| `STORAGE_TEST_DATABASE_URL` | unset | [`tests/conftest.py`](../../tests/conftest.py) | Enables the `db` tests (see [19](19-testing-and-quality.md)). |

## Configuration files

All paths are constants of [`src/conf/__init__.py`](../../src/conf/__init__.py).

| File | Constant | Model / reader | Content |
|---|---|---|---|
| [`llm.yaml`](../../src/conf/llm.yaml) | `LLM_CONFIG_PATH` | [`LLMSettings`](../../src/models/configuration/llm/llm_settings.py#L16) via [`LLMSettingsLoader`](../../src/llm/settings_loader.py#L19) | models, routing, budget |
| [`logger.yaml`](../../src/conf/logger.yaml) | `LOGGER_CONFIG_PATH` | `LoggingConfig` via [`load_logging_config`](../../src/logger/__init__.py#L21) | `dictConfig` schema |
| [`classification.yaml`](../../src/conf/classification.yaml) | `CLASSIFICATION_RULES_PATH` | `ClassificationRules` via [`SoftwareClassifier`](../../src/classifier/software_classifier.py#L27) | rules of the categories, audiences and delivery |
| [`taxonomy/taxonomy.yaml`](../../src/conf/taxonomy/taxonomy.yaml) | `TAXONOMY_SEED_PATH` | `Taxonomy` via [`TaxonomySeedLoader`](../../src/taxonomy/seed_loader.py#L23) | 29 domains, 195 categories, in en/ru/zh |
| [`taxonomy/label-seed.yaml`](../../src/conf/taxonomy/label-seed.yaml) | `LABEL_SEED_PATH` | `LabelSeed` | 170 known Russian and Chinese labels, with translations and links |
| [`taxonomy/prompts.yaml`](../../src/conf/taxonomy/prompts.yaml) | `TAXONOMY_PROMPTS_PATH` | `PromptSet` | the system prompts of the 3 LLM tasks |
| [`metrics/metrics.yaml`](../../src/conf/metrics/metrics.yaml) | `METRICS_CATALOG_PATH` | driver metric catalogue | 32 metric definitions |
| [`metrics/collectors.yaml`](../../src/conf/metrics/collectors.yaml) | `METRIC_COLLECTORS_PATH` | `CollectorCatalog` | where each provider is found (CIK, Wikidata, ASNs, repositories) |
| [`metrics/manual-metrics.yaml`](../../src/conf/metrics/manual-metrics.yaml) | `MANUAL_METRICS_PATH` | [`ManualMetricLoader`](../../src/storage/repositories/metrics/manual_metric_loader.py) | values typed by hand, each with its source URL (currently `values: []`) |
| [`metrics/drivers-help.yaml`](../../src/conf/metrics/drivers-help.yaml) | `DRIVERS_HELP_PATH` | GUI help of the drivers | roles, warnings, column guide |

## llm.yaml

```yaml
llm:                 # fallback model (routing absent or disabled)
  provider: anthropic
  model_name: claude-sonnet-5-5
  api_key: "ANTHROPIC_API_KEY"     # the NAME of the variable, never the key
  max_tokens: 8192
  input_rate_per_million: 2.0
  output_rate_per_million: 10.0
llm_routing:
  enabled: true
  default_profile: balanced
  profiles: {precise: …, balanced: …, fast: …}
  tasks:
    label_translation:      { profile: fast,     effort: low,    max_tokens: 8192 }
    item_classification:    { profile: balanced, effort: low,    max_tokens: 8192 }
    service_correspondence: { profile: balanced, effort: medium, max_tokens: 16384 }
llm_budget: { ceiling: 10.0, currency: USD, enforce: true }
batch_size: 50       # 1–200 labels or items per call
after_crawl: true    # run the tasks after each provider crawl
```

| Field | Model | Constraints |
|---|---|---|
| `provider` | `LLMProvider` | `anthropic` or `openai` |
| `max_tokens` | int | 1–128,000 |
| `effort` | `LLMEffort` | `low`, `medium`, `high`, `xhigh`, `max` |
| `temperature` | float, optional | ≤ 2.0. Rejected by the current Claude models, so it is not sent to them. |
| `cache_read_rate_per_million` | optional | defaults to a tenth of the input rate |
| `llm_routing.tasks.*` | `LLMTaskRoute` | `profile` must exist (`UnknownLLMProfileError`); only `effort` and `max_tokens` may be overridden |

The full behaviour (routing, budget, tasks) is in [15 — LLM layer](15-llm-layer.md).

## logger.yaml

| Section | Content |
|---|---|
| formatters | `detailed` (file) and `coloured` ([colorlog](https://github.com/borntyping/python-colorlog)). Both print the process, thread and asyncio `taskName`. |
| handlers | `console` (stdout, DEBUG) and `file` (`RotatingFileHandler`, `logs/poc-crawler.log`, 10 MiB × 5) |
| loggers | `asyncio`, `httpx`, `httpcore`, `urllib3` and `scrapling` at WARNING. Configuring `scrapling` removes its own console handler. |
| root | DEBUG, `[console, file]` |

[`setup_logging`](../../src/logger/__init__.py#L50) validates the file into `LoggingConfig`, creates the log folders and calls [`logging.config.dictConfig`](https://docs.python.org/3/library/logging.config.html#logging.config.dictConfig).

## classification.yaml and the taxonomy seed

| Key | Entries | Purpose |
|---|---|---|
| `delivery_audiences` | 9 | audience of a software by delivery method |
| `product_audiences` | 1 | `[developer-tool]` for a catalogue product with no known audience |
| `delivery_categories` | 7 | category of a software that nothing else classifies |
| `noise_labels` | 6 regexes | whole labels that are not categories (`products?`, `продукты`, `其他`…, in en, ru and zh) |
| `packaging_suffix` | 1 regex | strips " on Ubuntu 24.04", " Virtual Machine" before name matching |
| `audience_hints` | 2 | audiences read from the labels |
| `name_rules` | 79 | well-known products |
| `category_rules` | 199 | source label → taxonomy node |
| `keyword_rules` | 219 | name and description keywords (en, ru, zh) |

The seed files (`taxonomy.yaml`, `label-seed.yaml`, `classification.yaml`) are hashed together. They are applied again whenever the hash changes, and they never overwrite a person's edits (see [14 — Classification engine](14-classification-engine.md)).

## Metrics configuration

- `collectors.yaml` holds one entry per provider: `cik` (SEC filer), `wikidata` (Q-id), `asns` (PeeringDB) and `repositories` (GitHub). It also holds the `capex_concepts` fallback order of the XBRL concepts, and the **names** of the secret variables.
- `metrics.yaml` holds the 32 definitions, with these fields: `metric`, `label`, `family`, `scale` (count, amount or share), `unit`, `target`, `description` and `sources`.
- `manual-metrics.yaml` holds the values found by hand, each with its source URL. Quarters are written `YYYYQn`, and a yearly figure goes on the last quarter of its year.

See [16 — Analytics](16-analytics.md).

## VS Code launch configurations

[`.vscode/launch.json`](../../.vscode/launch.json) is checked by [`tests/test_vscode_launch.py`](../../tests/test_vscode_launch.py):

| Configuration | Runs |
|---|---|
| Crawler: run target | `src/main.py`, with `CRAWLER_TARGET` and `CRAWLER_SOURCE` picked from the inputs |
| Crawler: run target (step into libraries) | the same, with `justMyCode` off |
| GUI: catalogue explorer | module `gui.window.app` |
| Tests: all, Tests: current file | pytest |
| Tests: coverage report | pytest `--cov=src --cov-branch` |
| Tests: debug from Test Explorer | the `debug-test` purpose |

Their inputs:
- `crawlerTarget` offers the 32 providers plus `all`, with `scaleway` as the default;
- `crawlerSource` offers every `CrawlSource`, with `catalogue` as the default.

The test fails when either list drifts from the code.

## See also

- [10 — Architecture](10-architecture.md)
- [12 — Crawler framework](12-crawler-framework.md)
- [20 — Operations](20-operations.md): `install-stack`, `migrate-db`, troubleshooting.

[← Previous](10-architecture.md) · [Next →](12-crawler-framework.md)
