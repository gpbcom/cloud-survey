# poc-crawler

Crawls the **product catalogues** and **marketplaces** of 28 cloud providers from 10 countries, and the **cloud
market shares** published by Synergy Research Group. It writes JSON files and shows them in a PyQt6 desktop explorer.

- **Crawling:** [Scrapling](https://github.com/D4Vinci/Scrapling) spiders.
  - A stealth Chromium browser is used for the pages that need JavaScript or face anti-bot checks.
  - A browser-impersonating HTTP client is used for the JSON APIs of the marketplaces.
- **Politeness:**
  - `robots.txt` (including `Crawl-delay`) is obeyed everywhere.
  - Each crawler sends one request at a time, 1 s apart by default (3 s for China Mobile Cloud).
- **Parallelism:** several providers are crawled at the same time, 4 by default (`CRAWLER_CONCURRENCY`, or the
  "Parallel crawls" box of the GUI). Each website still sees one request at a time.
- **History:** every product and software keeps the dates it was added, updated and deleted (see below).
- **Progressive output:** a running crawl rewrites its file every 10 s with the items crawled so far.
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

The **whole catalogue** of each provider is extracted, including hosting, domains, e-mail and office products.

- **Sources:** each crawler reads the provider's main product listing, then complementary sources (menus, sitemaps,
  documentation directories, JSON APIs). It only adds the products not found yet.
- **Duplicates:** products are compared by normalized name (brand prefixes and notes ignored, any script) and by URL.
- **Product pages:** when a listing only gives names, each product page is read for its description.
- **Chinese providers:** the four Chinese-only catalogues keep their names and descriptions in Chinese.
- **China Mobile Cloud:** its website bans clients sending more than about one request per second. Its crawler is
  slow and retries for minutes. Run it on its own if a ban is active.

Each catalogue crawler lives in `src/crawler/cloud/<package>/crawler.py`. Its sources are described in the class
docstring.

## Marketplaces

For the providers having one, the software of their marketplace is extracted. Five providers have no marketplace but
offer one-click applications, and those lists are extracted instead: Gcore, Aruba, Krystal, Combell and Infomaniak.

- **Excluded:** professional or consulting services, datasets, hardware and courses.
- **Classification:** each software is classified by deterministic rules (`src/conf/classification.yaml`). In order of
  precedence:
  1. well-known products, recognized by name (e.g. Odoo → ERP, WooCommerce → e-commerce);
  2. the types of the marketplace's own categories, keeping only those the keywords confirm when a listing ticks
     many categories;
  3. the keywords of its name, added to the category types;
  4. the keywords of its description;
  5. otherwise `other`.

  Packaging suffixes such as "on Ubuntu 24.04" are ignored.
  - **Categories:** `developer-tool` and/or `end-user-software`.
  - **Types:** `ats`, `crm`, `erp`, `hris`, `accounting`, `ecommerce`, `cms`, … `other` (see
    `models.cloud.enums.SoftwareType`).
  - **Delivery method:** `saas`, `virtual-machine`, `container`, `kubernetes`, `api`, `ai-model`, `one-click-app`, …
- **Code:** each marketplace crawler lives in `src/crawler/cloud/<package>/marketplace.py`.
- **Duration:** about 115,000 listings in total. A full run takes several hours, mostly Microsoft (about 81,000
  apps, with a 2 s crawl delay), Baidu and Oracle.

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
- **Observed dates:** each crawl is compared with the previous file. Items are recognized by their page, then their
  name. The first crawl of a provider has nothing to compare with, so its observed dates stay unknown.
- **Deleted items:** they stay in the file with their `deleted_at`, and come back to life if they are listed again.
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
```

## Crawling

```bash
CRAWLER_TARGET=scaleway uv run python src/main.py                            # one catalogue
CRAWLER_TARGET=all uv run python src/main.py                                 # every catalogue
CRAWLER_SOURCE=marketplace CRAWLER_TARGET=civo uv run python src/main.py     # one marketplace
CRAWLER_SOURCE=both CRAWLER_TARGET=all uv run python src/main.py             # everything
CRAWLER_SOURCE=reclassify uv run python src/main.py                          # classify the stored software again
CRAWLER_SOURCE=statistics uv run python src/main.py                          # the market statistics
```

| Variable | Values |
|---|---|
| `CRAWLER_TARGET` | a `CloudProvider` value from the table above, or `all` (not needed by `reclassify` and `statistics`) |
| `CRAWLER_CONCURRENCY` | how many providers are crawled at the same time, 4 by default (each browser crawl opens its own window) |
| `CRAWLER_SOURCE` | `catalogue` (default), `marketplace`, `both`, `statistics` (the Synergy market shares), or `reclassify` (no crawl: the stored marketplace software is classified again with the current rules, e.g. after editing `src/conf/classification.yaml`) |

Output:
- catalogues go to `output/<provider>.json`;
- marketplaces go to `output/marketplaces/<provider>.json`;
- market statistics go to `output/stats/synergy.json`;
- logs go to the console and to `logs/poc-crawler.log` (rotating), configured in `src/conf/logger.yaml`.

Files are written progressively:
- **While a crawl runs:** every 10 s with the items crawled so far (`"in_progress": true`). The items not crawled yet
  are kept unchanged, and nothing is marked deleted.
- **Once it is over:** with every item, the missing ones marked deleted.
- **Empty or failed crawl:** the file keeps every item of the previous crawl.

The browser runs visibly (`headless=False`), so a window opens during the crawls that need it.

## GUI

```bash
uv run python -m gui.app      # or the "GUI: catalogue explorer" VS Code launch configuration
```

The explorer shows the following:
- **Sidebar:** the providers grouped under their country flag. Selecting a country or a provider filters the view.
- **Dashboard:** the products per provider.
- **Products table:** filtered by search and by country, with a details panel.
- **Logs:** the live log panel.

Crawls can be launched from the toolbar: the selected provider, the selected country, or everything. "Parallel crawls"
sets how many providers run at the same time.

The views follow the output files: when a file changes, only that file is read again. Products and software therefore
appear every few seconds during a crawl, and the sidebar marks a catalogue being crawled.

The tables show when each item was added and updated, with the origin of the date in the tooltip and the details
panel. "Show deleted" shows the items deleted from their website, struck through.

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
- the trend of the shares over the checked periods;
- the market size per period, with the growth in the tooltip.

"Refresh from Synergy" (or the crawl actions of the toolbar on this tab) crawls the statistics again.

## Tests and checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
uv run pytest                 # offline tests, 100% line and branch coverage
uv run pytest --live -m live  # smoke tests against the real websites (slow, opens the browser)
```

- **Offline tests:** they use trimmed snapshots of the real pages (`tests/fixtures/`).
- **Convention tests:** they enforce the project rules:
  - typing: `Dict`/`List`/`Optional`/`Union`, no `Any` or `object`;
  - class layout: internal helpers before public methods, callee before caller, `parse` last;
  - one exception module per package;
  - `field_validator(mode="before")`;
  - no semicolons in prose;
  - an ERROR log before every raise outside the models;
  - one class per GUI module.
