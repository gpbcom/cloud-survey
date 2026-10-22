# poc-crawler

Crawls the **product catalogues** and **marketplaces** of 32 cloud providers from 11 countries, and the **cloud
market shares** published by Synergy Research Group. It stores them in PostgreSQL (asynchronous SQLAlchemy) and shows
them in a PyQt6 desktop explorer.

- **Crawling:** [Scrapling](https://github.com/D4Vinci/Scrapling) spiders.
  - A stealth Chromium browser is used for the pages that need JavaScript or face anti-bot checks.
  - A browser-impersonating HTTP client is used for the JSON APIs of the marketplaces.
- **Politeness:**
  - `robots.txt` (including `Crawl-delay`) is obeyed everywhere.
  - Each crawler sends one request at a time, 1 s apart by default (3 s for China Mobile Cloud).
- **Parallelism:** several providers are crawled at the same time, 4 by default (`CRAWLER_CONCURRENCY`, or the
  "Parallel crawls" box of the GUI). Each website still sees one request at a time.
- **History:** every product and software keeps the dates it was added, updated and deleted (see below).
- **Progressive storage:** a running crawl writes its items every 10 s (or every batch of 2,000), only the new and
  changed ones.
- **Validation:** every product and software is checked by a Pydantic model.
- **Logging:** everything is logged: every product, every skipped entry, and an ERROR before every raised exception.

## Providers

| Country | Provider | `CRAWLER_TARGET` | Products (2026-10-16) |
|---|---|---|---|
| United States | Amazon Web Services | `amazon-web-services` | 321 |
| | Microsoft Azure | `microsoft-azure` | 235 |
| | Google Cloud Platform | `google-cloud-platform` | 205 |
| | IBM Cloud | `ibm-cloud` | 106 |
| | Oracle Cloud | `oracle-cloud` | 150 |
| France | OVHcloud | `ovh-cloud` | 136 |
| | Scaleway | `scaleway` | 80 |
| Belgium | Combell | `combell` | 56 |
| | Proximus NXT | `proximus-nxt` | 44 |
| Germany | STACKIT | `stackit` | 45 |
| | T Cloud Public (ex Open Telekom Cloud) | `t-cloud-public` | 62 |
| Italy | Aruba Cloud | `aruba-cloud` | 41 |
| | Seeweb | `seeweb` | 26 |
| Luxembourg | Gcore | `gcore` | 47 |
| | DEEP (POST Luxembourg) | `deep-post-luxembourg` | 57 |
| Spain | Arsys | `arsys` | 48 |
| | Gigas | `gigas` | 18 |
| Switzerland | Exoscale | `exoscale` | 28 |
| | Infomaniak | `infomaniak` | 42 |
| United Kingdom | Civo | `civo` | 27 |
| | Krystal (incl. Katapult) | `krystal` | 25 |
| China | Alibaba Cloud (international site) | `alibaba-cloud` | 247 |
| | Huawei Cloud (international site) | `huawei-cloud` | 165 |
| | Tencent Cloud (international site) | `tencent-cloud` | 216 |
| | Baidu AI Cloud (Chinese) | `baidu-ai-cloud` | 254 |
| | Volcano Engine (Chinese) | `volcano-engine` | 130 |
| | China Telecom Cloud / Tianyi (Chinese) | `china-telecom-cloud` | 170 |
| | China Mobile Cloud (Chinese) | `china-mobile-cloud` | see below |
| Russia | Yandex Cloud | `yandex-cloud` | see below |
| | VK Cloud (ex Mail.ru Cloud Solutions) | `vk-cloud` | see below |
| | Cloud.ru (ex SberCloud) | `cloud-ru` | see below |
| | Selectel | `selectel` | see below |

The **whole catalogue** of each provider is extracted, including hosting, domains, e-mail and office products.

- **Sources:** each crawler reads the provider's main product listing, then complementary sources (menus, sitemaps,
  documentation directories, JSON APIs). It only adds the products not found yet.
- **Duplicates:** products are compared by normalized name (brand prefixes and notes ignored, any script) and by URL.
- **Product pages:** when a listing only gives names, each product page is read for its description.
- **Chinese providers:** the four Chinese-only catalogues keep their names and descriptions in Chinese.
- **Russian providers:** the names, descriptions and categories are kept as their websites give them, in Russian when
  the English site is missing or poorer.
- **China Mobile Cloud:** its website bans clients sending more than about one request per second. Its crawler is
  slow and retries for minutes. Run it on its own if a ban is active.

Each catalogue crawler lives in `src/crawler/cloud/<package>/crawler.py`. Its sources are described in the class
docstring.

## Marketplaces

For the providers having one, the software of their marketplace is extracted. Five providers have no marketplace but
offer one-click applications, and those lists are extracted instead: Gcore, Aruba, Krystal, Combell and Infomaniak.

- **Excluded:** professional or consulting services, datasets, hardware and courses.
- **Classification:** each software (and each catalogue product) is filed in the unified taxonomy, see
  [Unified categories](#unified-categories). The rules also give:
  - **Audiences** (`categories`): `developer-tool` and/or `end-user-software`, those of its taxonomy nodes. A product
    of no known category gets `product_audiences` (`developer-tool`: a cloud service is built on by developers).
  - **Delivery method:** `saas`, `virtual-machine`, `container`, `kubernetes`, `api`, `ai-model`, `one-click-app`, …
- **Marketplace categories:** each software keeps the categories of the marketplace itself in two forms:
  - `marketplace_categories`: the flat labels, read by the classifier;
  - `marketplace_category_paths` (optional): the categories in the marketplace's own taxonomy, each with the categories
    above it and the marketplace's identifier, e.g. `{"path": ["AI Agents & Tools", "Content Creation"], "id": "…"}`.
    It is `null` when the marketplace shows no category (Gcore). A software found under several categories (GCP and
    Azure query each category) keeps every path, the parents of a deeper path being dropped. GCP's "Managed
    Services" and "Other" categories are recorded as paths only, never as flat labels, because they say nothing
    about the software.
- **Code:** each marketplace crawler lives in `src/crawler/cloud/<package>/marketplace.py`.
- **Duration:** about 115,000 listings in total. A full run takes several hours, mostly Microsoft (about 81,000
  apps, with a 2 s crawl delay), Baidu and Oracle.

## Unified categories

Products and software share one English taxonomy, **Domain > Category** (29 domains, 224 nodes, `other` being a
hidden last resort), and an item may belong to several categories at once. It is stored in SQL with its English,
Russian and Chinese names, seeded from `src/conf/taxonomy/taxonomy.yaml`.

Two layers:
1. **Categories** (`service_categories`, `service_domains` on each item, GIN-indexed): the curated taxonomy, filtered,
   counted and charted on both views.
2. **Source labels** (`source_label_ids`): the categories of the providers, as they write them, in any language. They
   are stored once per normalized key (`Databases`, `DataBases` and `DATABASE` are one label) with an English name.
   Labels sharing an English name are aliases: "Базы данных" (translated "Databases") counts with "Databases".

How an item gets its categories, the first answer winning:
1. a person set them (`categories_source` = `user`): they are kept;
2. the taxonomy nodes linked to its source labels (a label may link a domain only, e.g. "Data platform");
3. the rules of `src/conf/classification.yaml`: well-known names, label rules, name and description keywords in
   English, Russian and Chinese (packaging suffixes such as "on Ubuntu 24.04" or " Virtual Machine" ignored);
4. its delivery method (a virtual-machine image of nothing else is a machine image);
5. the language model, when configured (kept until the content of the item changes);
6. `other`.

Labels and links:
- A crawl stores the labels it has never seen at once, with the links the rules give them. Parallel crawls store each
  new label once (`INSERT … ON CONFLICT DO NOTHING`, keys sorted).
- A non-English label waits for its English name (`pending`) unless the label seed gives it:
  `src/conf/taxonomy/label-seed.yaml` translates and links the known Russian and Chinese labels, and marks the noise
  ("Продукты", "其他", …).
- Links come from the rules, the seed, the language model or a person. Recomputing the rules never touches the other
  ones, and an exclusion made by a person survives every recomputation.
- When the taxonomy changes during a crawl, the items of the crawled provider are categorized again once it is over.

The seed (`taxonomy.yaml`, `label-seed.yaml`, `classification.yaml`) is applied after `migrate-db upgrade`, by
`migrate-db seed`, by `CRAWLER_SOURCE=reclassify`, and before the first write after the files changed. It never
overwrites what a person edited.

### Language model

A language model translates the pending labels and files the items left under `other` (rung 5 above). It is
optional: without an API key nothing is sent, the labels wait in the Categories manager and the items stay
unclassified. The settings are in `src/conf/llm.yaml` (or the file named by `CRAWLER_LLM_CONFIG`), modelled on the
mega-trends `rt-llm` settings, without Langfuse:
- `llm`: the fallback model;
- `llm_routing`: the profiles (`precise` Claude Opus 5.5, `balanced` Claude Sonnet 5.5, `fast` Claude Haiku 5.5) and
  the profile of each task: `label_translation` uses `fast`, `item_classification` and `service_correspondence`
  use `balanced`;
- `llm_budget`: the cost ceiling (10 USD by default). Every call is recorded in `llm_usage` with its tokens and cost,
  and no call is sent once the ceiling is reached;
- `batch_size` (50 labels or items per call) and `after_crawl` (run both tasks after each crawl).

`api_key` holds the **name** of the environment variable carrying the key (`ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`
for an `openai` profile), never the key itself:

```bash
export ANTHROPIC_API_KEY=...                               # enables both tasks
CRAWLER_SOURCE=translate uv run python src/main.py         # translate every pending label, then classify "other"
```

The tasks run after each crawl of a provider (a failure is logged, never a failed crawl), with
`CRAWLER_SOURCE=translate`, or from the Categories manager ("Translate pending labels", "Classify unclassified
items", shown only when a key is set, with what was spent of the budget). Concurrent runs never take the same label
(`FOR UPDATE SKIP LOCKED`). A batch whose call fails is retried by a later run, up to three attempts. The answers
never overwrite what a person set, and only taxonomy slugs that exist are kept.

## Service correspondences

The **Correspondences** tab maps the equivalent catalogue services of the providers (Amazon EC2, Azure Virtual
Machines and Google Compute Engine are the same service), matched by the language model:
- **Service concepts.** The services are grouped into concepts shared by the providers ("Managed Kubernetes",
  "Object storage"…), category by category of the unified taxonomy. A concept may hold several services of one
  provider (a 2:1 or 3:1 correspondence), a service may belong to two concepts, and a service matching part of a
  concept only is *partial*. Every service filed by the model carries its confidence.
- **Storage.** `service_concepts`, `concept_members` (with `excluded` for the services a person removed: the model
  never files them there again) and `correspondence_checks` (the content fingerprint each service was matched for).
- **Updates.** A listed product is matched again when it is new, when its content changes or when it moves to
  another category: after each catalogue crawl (for the crawled provider), with `CRAWLER_SOURCE=correspond` (or
  `translate`, as its third step), or with "Match with AI" in the tab. Two runs never match the same category at once
  (an advisory lock). A failed call is tried again by a later run, three times at most.
- **Diagram.** One column per chosen provider (2 to 6, with presets: the largest catalogues, the leader of each bloc,
  the largest providers of a bloc), one row per concept, grouped by domain. The services of adjacent columns are
  joined by curves coloured by correspondence class (1:1, 2:1, 3:1, n:1), dashed when partial, thicker when the model
  is surer. A provider without a service of the concept shows an empty slot. Hovering a row dims the others,
  Ctrl + wheel zooms, and the diagram exports to PNG or CSV.
- **Filters.** Taxonomy categories, text, correspondence classes, coverage (offered by every column, missing in a
  column, unique to one column), equivalent or partial services, AI confidence, AI or by hand, audience, deleted
  services.
- **Coverage matrix.** For each pair of providers, the share of the services of one with an equivalent at the other.
  Clicking a cell compares the two providers, their gaps first.
- **Editing.** The details panel renames, merges or deletes a concept, adds a service to it, marks a service
  equivalent or partial, removes it, or has its category matched again. What a person sets is never changed by the
  model.

## Rise drivers

Which criteria are predominant in the rise of a cloud provider: the method, the criteria gathered, those missing
and where to find them, and the first findings are in [docs/analysis/rise-drivers.md](docs/analysis/rise-drivers.md).

- **Measures.** `provider_metrics` holds one value per provider, quarter, metric and source. The `derived` and
  `synergy` measures are computed from the stored datasets by `CRAWLER_SOURCE=metrics` (and before a run in the GUI
  when a dataset was written). The values found by hand (annual reports, analyst press releases) go in
  `src/conf/metrics/manual-metrics.yaml`, with their source URL. The definitions (label, family, scale, sources,
  whether a metric can be a target) are in `src/conf/metrics/metrics.yaml`.
- **Metrics crawlers.** `CRAWLER_SOURCE=metrics` also crawls public APIs, one crawler per source in
  `src/crawler/metrics/<source>/` (built like the cloud crawlers, on `BaseCloudCrawler`): SEC EDGAR (capex facts of
  the groups), Wikidata (founding dates, employee counts), PeeringDB (networks and their exchanges and facilities)
  and GitHub (repository stars). The crawlers only stream the facts as the sources state them. `src/analytics/metrics/`
  computes them into the provider metrics (quarters from the year-to-date filings, age, distinct counts, sums).
  Where each provider is found is in `src/conf/metrics/collectors.yaml`. Set `CRAWLER_SEC_USER_AGENT` to a user agent
  naming a contact (SEC asks for one), and optionally `GITHUB_TOKEN` (60 requests an hour without it) and
  `PEERINGDB_API_KEY` (anonymous queries are throttled). The `robots.txt` rules are obeyed. A source yielding nothing
  is skipped, and its stored values are kept.
- **Analysis tab, "Rise drivers".** Pick a target, criteria (at most 16, about one per 10 providers is stable),
  controls, the latest quarter or a panel of every quarter with a lag, then Run. The cards show the Spearman
  correlations (95% bootstrap intervals, Benjamini-Hochberg significance, partial correlation), the share of the
  explained variance of each criterion (Shapley split of the R², with intervals), the target against the
  predominant criterion, a table of every figure (standardized β, p-values, leave-one-out R², Granger p in a panel)
  and the warnings. "Export CSV" saves the observations.

## History: added, updated and deleted dates

Every product and software has three optional dates, `null` when unknown:

| Field | Meaning | Source (`added_from` / `updated_from`) |
|---|---|---|
| `added_at` | when it appeared | `website` when the provider publishes it, else `crawl`: the first crawl that found it |
| `updated_at` | when it last changed | `website` when the provider publishes it, else `crawl`: the first crawl that saw its name, description, page, pricing, publisher, delivery or marketplace categories change |
| `deleted_at` | when it disappeared | always observed by a crawl |

- **Website dates:**
  - **Catalogues:** AWS (published and updated), Scaleway, IBM and Oracle documentation pages (updated), and STACKIT,
    T Cloud Public and OVHcloud (updated, from their sitemap, for the products found through it).
  - **Marketplaces:** Oracle and OVHcloud (both dates), Huawei (both), IBM (updated), T Cloud Public, Volcano Engine and
    Tencent (added; Tencent's comes from its product identifiers, read in China's timezone).
  - **Other sources:** they publish no date.
- **Observed dates:** each crawl is compared with the stored items. Items are recognized by their page, then their
  name. The first crawl of a provider has nothing to compare with, so its observed dates stay unknown.
- **Versions:** a version of an item (its content without the dates) is stored for each crawl which found it new or
  changed (`product_versions`, `software_versions`).
- **Deleted items:** they stay stored with their `deleted_at`, and come back to life if they are listed again.
  - A crawl finding less than half of the previous items is presumably partial: nothing is marked deleted then.
  - The GUI hides the deleted items, and the "Show deleted" checkbox shows them struck through.

## Market statistics

The cloud market shares come from the press releases of [Synergy Research Group](https://www.srgresearch.com/articles),
the reference used by most of the press. The crawler lives in `src/crawler/stats/`.

- **Sources:** the `/articles` listing (2023 onwards), plus the older article addresses known to the Wayback Machine.
  The articles themselves are always read on the live website.
- **Figures:** they are read from the text of the articles, the charts being images.
  - **Worldwide, cloud infrastructure services** (IaaS, PaaS and hosted private cloud): the quarterly shares of
    Amazon, Microsoft and Google, the market size and the growth.
  - **Worldwide, public IaaS and PaaS:** the combined share of the top three.
  - **Europe:** the share of the big three, of the European providers, of SAP and of Deutsche Telekom, in euros, for
    the years or half-years Synergy publishes.
- **Others:** Synergy only quantifies a few players. The rest of the market is shown as "Others (computed)": 100% minus
  the named shares. The providers it only names or ranks (e.g. "fourth-placed Alibaba") are listed under the charts.
- **Methodology break:** Synergy reclassified some revenues in Q3 2024, which lowered Microsoft's share. The trend chart
  marks it.

## Setup

```bash
uv sync
uv run patchright install chromium   # the stealth browser
uv run install-stack                 # PostgreSQL (Docker Compose) + the database migrations
uv run install-stack --import-json   # the same, then import the JSON files of the former file storage (output/)
```

`install-stack` can be run again at any time: it starts what is stopped and applies the missing migrations. Its
options:
- `--no-docker`: use the server of `CRAWLER_DATABASE_URL` instead of starting the Compose service;
- `--test`: also start (and migrate) the throw-away test server, on port 5433;
- `--import-json [FOLDER]`, `--replace`: import the JSON files, replacing the stored datasets.

## Storage

The crawled data is stored in PostgreSQL through asynchronous SQLAlchemy (asyncpg). The code lives in `src/storage/`.

| Table | Content |
|---|---|
| `products`, `software` | one row per item, with its history dates, its match key hashes and its content hash |
| `product_versions`, `software_versions` | the content of an item each time a crawl found it new or changed |
| `crawls` | every crawl: dates, status (`succeeded`, `partial`, `empty`, `failed`, `abandoned`, `imported`), counters |
| `datasets` | the state of each catalogue, marketplace and statistics source, polled by the GUI |
| `market_reports` | the market statistics |
| `taxonomy_nodes`, `taxonomy_state` | the unified taxonomy (domains and categories, en/ru/zh) and its revision |
| `source_labels`, `label_links`, `label_sightings` | the categories of the providers, their links to the taxonomy, where they were seen |
| `llm_usage` | the calls to the language model, with their tokens and cost |
| `service_concepts`, `concept_members`, `correspondence_checks` | the equivalent services of the providers (see Service correspondences) |
| `provider_metrics` | the measures of the providers per quarter, with their source (see Rise drivers) |

How it scales to millions of items:
- **Incremental writes:** the items are written by batches. The new ones are inserted and the changed ones updated,
  and the unchanged ones are not written at all.
- **Indexes:** the items are found by provider and fixed-size hashes of their match keys, read by revision, and
  searched by trigram indexes of the names.
- **Space for updates:** the tables leave room in their pages (`fillfactor`) so that updates stay in place.
- **Locks:** a PostgreSQL advisory lock keeps each dataset written by a single crawl at a time.

The repositories (`Storage.catalogues`, `Storage.marketplaces`) offer:
- `create`, `read`, `update` and `delete` to change items by hand;
- `list`, which reads pages of items filtered, ordered and counted by the server (`ItemQuery`, `Page`);
- `facets`, for the counts of the marketplace software by provider, audience, taxonomy domain and delivery;
- `category_counts` and `label_counts`, for the counts of the items by taxonomy node and by source label;
- `recategorize`, which files the stored items of a provider again (all, or those of some labels or nodes).

| Variable | Default |
|---|---|
| `CRAWLER_DATABASE_URL` | `postgresql+asyncpg://crawler:crawler@localhost:5432/poc_crawler` |
| `CRAWLER_DATABASE_POOL_SIZE`, `CRAWLER_DATABASE_MAX_OVERFLOW` | 5, 30 (each running crawl holds one connection) |
| `CRAWLER_DATABASE_BATCH_SIZE` | 2000 items per batch |
| `CRAWLER_DATABASE_ECHO` | off (`1` logs every SQL statement) |

Migrations (Alembic, in `scripts/migrations/`) are run with `uv run migrate-db`:

```bash
uv run migrate-db upgrade              # apply the migrations (head by default), then the taxonomy seed
uv run migrate-db seed [--force]       # apply the taxonomy seed (when its files changed, or always with --force)
uv run migrate-db downgrade base       # revert them all
uv run migrate-db current              # the revision of the database
uv run migrate-db history              # the migrations
uv run migrate-db revision -m "Add x" --autogenerate   # write a new migration (to review), numbered after the head
uv run migrate-db check                # fail when the tables and the database schema differ
```

## Crawling

```bash
CRAWLER_TARGET=scaleway uv run python src/main.py                            # one catalogue
CRAWLER_TARGET=all uv run python src/main.py                                 # every catalogue
CRAWLER_SOURCE=marketplace CRAWLER_TARGET=civo uv run python src/main.py     # one marketplace
CRAWLER_SOURCE=both CRAWLER_TARGET=all uv run python src/main.py             # everything
CRAWLER_SOURCE=reclassify uv run python src/main.py                          # classify the stored items again
CRAWLER_SOURCE=statistics uv run python src/main.py                          # the market statistics
CRAWLER_SOURCE=import-json uv run python src/main.py                         # import output/*.json into the database
CRAWLER_SOURCE=translate uv run python src/main.py                           # the language model tasks (see above)
CRAWLER_SOURCE=correspond uv run python src/main.py                          # match the equivalent services only
CRAWLER_SOURCE=metrics uv run python src/main.py                             # compute the provider metrics again
```

**HTTPS certificates:** the HTTP sessions verify the websites against certifi's certificate authorities, merged with
the bundle named by `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` or `SSL_CERT_FILE` (for example a company proxy authority).
The merged file is `~/.cache/poc-crawler/ca-bundle.pem`. Without the merge, an outdated system bundle in
`REQUESTS_CA_BUNDLE` lacks recent roots, such as the Sectigo root of scaleway.com, and every page of those websites fails.

| Variable | Values |
|---|---|
| `CRAWLER_TARGET` | a `CloudProvider` value from the table above, or `all` (not needed by `reclassify`, `statistics`, `translate`, `correspond` and `metrics`) |
| `CRAWLER_LLM_CONFIG` | another language model settings file than `src/conf/llm.yaml` |
| `CRAWLER_CONCURRENCY` | how many providers are crawled at the same time, 4 by default (each browser crawl opens its own window) |
| `CRAWLER_SOURCE` | `catalogue` (default), `marketplace`, `both`, `statistics` (the Synergy market shares), `reclassify` (no crawl: the taxonomy seed is applied, the source labels are linked again with the current rules, then the stored marketplace software and catalogue products are categorized again, e.g. after editing `src/conf/classification.yaml`; about 5 minutes for 110,000 software, followed by `VACUUM (ANALYZE) software, products`), `import-json` (no crawl: the JSON files of the former file storage are imported, from `CRAWLER_IMPORT_DIR`, `output` by default, replacing the stored datasets when `CRAWLER_IMPORT_REPLACE=1`), `translate` (no crawl: the language model translates the pending labels, categorizes the unclassified items, then matches the equivalent services, see Language model), `correspond` (no crawl: the equivalent services only, see Service correspondences), or `metrics` (no crawl: the measures of the providers computed again from the stored datasets, and the manual ones read again, see Rise drivers) |

Output:
- everything goes to the PostgreSQL storage (see Storage);
- logs go to the console and to `logs/poc-crawler.log` (rotating), configured in `src/conf/logger.yaml`.

Crawls are written progressively:
- **While a crawl runs:** every 10 s (or every 2,000 items), the new and changed items crawled so far. The dataset is
  marked in progress, and nothing is marked deleted.
- **Once it is over:** the stored items the crawl did not find are marked deleted (unless it looks partial).
- **Empty or failed crawl:** the items written so far are kept, and nothing is marked deleted.

The browser runs visibly (`headless=False`), so a window opens during the crawls that need it.

## GUI

```bash
uv run python -m gui.window.app      # or the "GUI: catalogue explorer" VS Code launch configuration
```

The explorer shows the following:
- **Sidebar:** the providers grouped under their country flag. Selecting a country or a provider filters the view.
- **Dashboard:** the headline figures, the products per provider and the catalogue trends (see Charts below).
- **Products table:** filtered by search, country and cloud provider, with a details panel. The provider filter
  lists the providers of the chosen country with their product count, and follows the sidebar. The category picker
  filters on the unified categories. "More filters" adds the texts, the source label (the category the catalogue
  gives, translated, aliases included), the audience (developer tool only, end-user software only, or both) and the
  dates.
- **Logs:** the live log panel.

Crawls can be launched from the toolbar: the selected provider, the selected country, or everything. "Parallel crawls"
sets how many providers run at the same time.

The views follow the storage: every 2 s the GUI reads the state of the datasets, and refreshes only those which
changed. Products and software therefore appear every few seconds during a crawl, and the sidebar marks a catalogue
being crawled.

The GUI never loads a whole catalogue or marketplace:
- **Tables:** they are read page by page, 200 rows at a time, at most 8 pages kept in memory. They are filtered,
  ordered and counted by the server.
- **Figures and filter counts:** they are counted by the server.
- **Threads:** the database is read in a dedicated thread, so the window never waits for it.

The tables show when each item was added and updated, with the origin of the date in the tooltip and the details
panel. "Show deleted" shows the items deleted from their website, struck through.

The **Marketplaces** tab filters the software on every field:
- **Main row:** search (name and publisher, optionally the descriptions), bloc, country, marketplace, providers,
  categories (the unified taxonomy: a fully ticked domain filters on the whole domain), audience, delivery, "Show
  deleted".
- **Cloud provider filters:** they combine, so the table shows the software of the providers matching all of them:
  - **Bloc:** the geopolitical bloc of the provider (United States, European Union, China, Russia, other).
  - **Country** and **marketplace:** one country, one provider.
  - **Providers:** a drop-down of the providers under their country, with their software count, where several can
    be ticked at once. It only offers the providers of the chosen bloc and country. A provider hidden this way keeps
    its tick for later.
- **"More filters":**
  - texts contained in the name, description or page address;
  - the publisher, picked among the most frequent ones;
  - the source label: the category the marketplace gives, translated, with its aliases (e.g. "Базы данных" with
    "Databases"), picked with its count;
  - the audience: developer tool only, end-user software only, or both;
  - ranges of the added, updated and deleted dates;
  - where the dates come from (the website, a crawl, or unknown) and whether they are approximate (and why).

Every filter runs on the server, so the counts, the chart and the table always describe the matching software.

Products and software can be **created, edited and deleted by hand**. The New, Edit and Delete buttons are in the
filter row of the products and above the software table, and also in the right-click menu of the table. Several rows can be selected at once (Shift or Ctrl+click,
Ctrl+A for the whole table):
- **New (Ctrl+N):** a form for one item and its provider.
- **Edit (F2):**
  - **One row:** its form. The provider and the dates are kept.
  - **Several rows:** a bulk form where only the ticked fields change on every selected item (the name stays
    unique to each).
- **Delete (Del):** removes the selected items and their history, once confirmed.

A selection may cover rows that were never read, such as a whole table of 70,000 software. Their identifiers are
read from the server with the table's filters and order, so nothing more is loaded into memory. Changes are refused
while the provider is being crawled: a warning says so, and nothing is written.

**Bulk selection** ("Select…", Ctrl+Shift+A, in both tabs) chooses items by criteria rather than by rows, in a
dedicated dialog:
- **Criteria:**
  - the cloud providers, ticked under their country (a country ticks all its providers);
  - the search text, and whether the listed items, the deleted ones, or both are chosen;
  - the unified categories, ticked in the taxonomy tree (a fully ticked domain picks the whole domain);
  - for software, the audiences and delivery methods;
  - every other field: texts, publisher, source label, dates and their precision.
- **Start:** the dialog opens with the main filters of the table.
- **Count:** the server counts the matching items live, as the criteria change.
- **Actions:**
  - **Show in the table:** the table shows the chosen items only. Its filters are disabled until "Selection ✕"
    clears the selection.
  - **Export:** writes the chosen items to a CSV, JSON or JSON lines file. They are streamed from the server batch by
    batch, and the file appears only once complete.
  - **Delete:** removes the chosen items and their history, once confirmed. The server deletes them without reading
    them, and refuses while one of their providers is being crawled.

Neither the export nor the deletion loads the chosen items into memory, however many there are.

The **Marketplaces** menu (menu bar or toolbar button) lists the 22 marketplaces under their country flag, with the
number of software of their last extraction. Check one or several of them, then choose "Extract the N selected
marketplaces": they are crawled in the background, several at a time, and the Marketplaces tab refreshes.

The **Statistics** tab shows the cloud market shares. Its checkboxes select the perimeter:
- **Region:** worldwide and/or Europe.
- **Segment:** cloud infrastructure services and/or public IaaS + PaaS.
- **Providers:** the players Synergy quantifies, and the computed Others.
- **Period:** the quarters, half-years or years, with "Latest" and "All" shortcuts.

It shows the following charts:
- the shares of the latest checked period, one group per region and segment;
- a configurable chart of the checked reports, first the market share race (see Charts below);
- the market size per period, with the growth in the tooltip.

"Refresh from Synergy" (or the crawl actions of the toolbar on this tab) crawls the statistics again.

### Charts

The charts serve competitive analysis, forecasts and geopolitics. Every tab holds its charts in collapsible cards:
- **Collapsing:** click a card title (or press Space on it) to fold the chart. "Expand all" and "Collapse all" fold
  every chart of the tab.
- **Scrolling:** the charts keep their size and the tab scrolls. On the Products and Marketplaces tabs, a splitter
  sets how much room the charts take above the table.
- **Memory:** the folded cards and the chosen axes are remembered from one session to the next.

The configurable charts are on the Products (catalogue trends), Marketplaces (marketplace analysis) and Statistics
tabs, and five of them on the **Analysis** tab, which compares the datasets with each other. Each one has:
- **Kind:** Line, Area (stacked), Bubble (competitive positioning), Heatmap or Mix (100% bars).
- **Y, X and By:** the metric of each axis, and what each series stands for. The x axis is either time (report
  period, publication date, year, quarter, month, crawl date) or another metric. For example, the market share
  against the marketplace size gives one point per provider and quarter.
- **Series:** players, providers, geopolitical blocs (United States, European Union, China, Russia, other countries),
  delivery methods, audiences, taxonomy domains or categories. The audience puts each item in one class: developer
  tool only, end-user software only, or both, so that the shares add up to 100 and the items meant for both are
  shown apart. An item in several categories (or domains) counts in each. The products are split by audience, domain
  and category too (not by delivery method).
- **Charts:** one chart, or one small chart per provider, bloc, delivery method, audience, domain or category (small
  multiples). Charts saved with the former software types read them as categories.
  The small charts share the series, their colours and the time axis, under one legend. They split the stored items
  counted over years, quarters or months (lines and areas).
- **Options:** shown as values, share of the total, indexed to 100, year-on-year change or rank (a bump chart).
  Also the number of series shown, the forecast, and logarithmic axes for the bubbles.
- **Views:** ready-made charts grouped by question: competitive analysis, forecast, geopolitics.
- **Export:** the picture (PNG, clipboard) or the data (CSV, clipboard), also in the right-click menu.

**Zoom:** every chart and graph zooms:
- **Buttons:** ＋ and － in the header of each configurable chart zoom around its middle, and ⟲ shows the whole
  chart again (every small chart of a split chart at once).
- **Gestures:** Ctrl + wheel (or a pinch) zooms around the mouse, and Ctrl + Shift + wheel zooms the y axis only.
  Dragging a rectangle zooms into it. A double-click or Escape shows everything again.
- **Scrolling:** a zoomed chart scrolls within its data with the wheel (Shift + wheel or a sideways swipe for the
  other axis) or a middle-button drag. Over a chart which is not zoomed, the wheel scrolls the page.
- **What zooms:** the time charts zoom their time axis, the bubble charts and heatmaps both axes (rows and columns of
  a heatmap), the mixes their shares. The bar charts zoom their values from zero, so that the small bars can be
  compared, and the market size chart its periods.
- **Persistence:** the zoom is kept while the data refreshes (during a crawl), and reset when the axes change. The
  small charts of a split chart zoom their time axis together.
- **Widen:** it makes a chart at least 1.5 times as wide as the view, with every name in full, and the chart scrolls
  sideways. For a split chart, the small charts get twice as wide, fewer per row. Widened or not, the charts share
  the whole width of their card.
- **Layout:** the chart cards stick together and to the table below them. A collapsed card, or a chart which keeps
  its natural height, gives the free height to the table, never leaving an empty band.

**Domain mix over time, by provider** ("Views" of the Marketplaces charts, and on the Analysis tab): one stacked
area per provider of the share of each taxonomy domain in its listed software, quarter by quarter. Every provider
shows the same 8 largest domains (the others merged), so that the providers can be compared. A provider whose
software is all dated by the same crawl shows a single stacked column. A software of several domains counts in each.

**Software per domain** (Marketplaces tab): the matching software of each taxonomy domain, the largest first, in the
colour of its main audience.

**Audience analyses** (who the software is for: developers, business users, or both), in the "Views" of the
Marketplaces charts:
- **Developer tools vs end-user software (and both) over time:** the stacked shares of the three audiences.
- **Audience mix by provider:** one 100% bar per provider, also on the Analysis tab.
- **Audience mix over time, by provider:** one small chart per provider.

The "Both audiences" card of the Marketplaces tab counts the matching software meant for both, and its share.

The options which do not go with the others are shown disabled, with the reason as tooltip. For example, the market
share is not known per delivery method, and an area needs a time axis. A chart can therefore not be configured
into nonsense. Hovering a chart shows every series at the nearest x value. Clicking a legend entry hides or shows its
series.

Metrics and their sources:
- **Market statistics:** market share, revenue (share × market size), market size, 12-month market size and growth.
  Synergy quantifies AWS, Azure, Google Cloud and T Cloud only.
- **Stored items, per bucket:** added, deleted and listed (a running total). Items without a published date are dated
  by the crawl which first found them, and the footnote says so.
- **Crawl records:** updated (and added, deleted, listed per crawl date). They start with the first crawl stored in the
  database: imports are not counted.
- **Marketplaces:** publishers, counted from their first listing.

The forecast is a trend, not a prediction. It is a least-squares fit of the last 8 points of each series, projected
4 steps ahead. The sizes, which compound, are fitted as a constant growth rate. The legend shows the yearly trend,
and the forecast is dashed after a "forecast" line.

The computation lives outside the GUI, in `src/analytics/`: the axis rules, presets, time axis, forecaster,
transforms and the loaders. The queries live in `src/storage/repositories/trends/`.

## Tests and checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run install-stack --test   # the throw-away PostgreSQL of the database tests (port 5433)
STORAGE_TEST_DATABASE_URL=postgresql+asyncpg://crawler:crawler@localhost:5433/poc_crawler_test uv run pytest
uv run pytest --live -m live  # smoke tests against the real websites (slow, opens the browser)
```

- **Database tests:** the tests marked `db` need `STORAGE_TEST_DATABASE_URL` and are skipped without it. Each test
  worker creates its own database from `template0`, migrated to the head revision, and drops it at the end.

- **Offline tests:** they use trimmed snapshots of the real pages (`tests/fixtures/`).
- **Layout:** the tests mirror `src/`, e.g. `tests/crawler/cloud/aws/` for the AWS catalogue and marketplace
  crawlers, and `tests/conventions/` for the project rules. No folder holds more than 5 Python files.
- **Convention tests:** they enforce the project rules:
  - typing: `Dict`/`List`/`Optional`/`Union`, no `Any` or `object`;
  - class layout: internal helpers before public methods, callee before caller, `parse` last;
  - one exception module per package;
  - `field_validator(mode="before")`;
  - no semicolons in prose;
  - an ERROR log before every raise outside the models;
  - one class per GUI module.
