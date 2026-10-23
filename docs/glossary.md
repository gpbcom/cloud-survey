[↑ Docs index](README.md) · Glossary

# Glossary

The terms used across the documentation and the code, in alphabetical order. Each entry links to the chapter that
explains it best.

| Term | Meaning | Chapter |
|---|---|---|
| **Abandoned crawl** | A crawl still marked `running` when a new crawl of the same dataset starts (its process died). The new crawl marks it `abandoned`. | [13-storage.md](technical/13-storage.md) |
| **Added / updated / deleted dates** | The three history dates of every product and software (`added_at`, `updated_at`, `deleted_at`), `null` when unknown. | [03-history-and-versions.md](functional/03-history-and-versions.md) |
| **Advisory lock** | A PostgreSQL lock on a number pair, not on a row. It keeps one crawl per dataset, one seeding and one AI matching per category at a time. See [PostgreSQL advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS). | [13-storage.md](technical/13-storage.md) |
| **Alias (label)** | Two source labels sharing an English name, or merged by a person: "Базы данных" counts with "Databases". | [04-categories.md](functional/04-categories.md) |
| **Audience** | Who an item is for: `developer-tool`, `end-user-software`, or both. Stored in the `categories` column. | [04-categories.md](functional/04-categories.md) |
| **Baseline** | Whether a provider had stored items before a crawl. The first crawl has none, so its observed dates stay unknown. | [03-history-and-versions.md](functional/03-history-and-versions.md) |
| **Big three** | Amazon, Microsoft and Google, whose combined share Synergy publishes. | [07-market-statistics.md](functional/07-market-statistics.md) |
| **Bloc** | The geopolitical bloc of a provider's country: United States, European Union, China, Russia, other (`GeoBloc`). | [01-overview.md](functional/01-overview.md) |
| **Bulk selection** | Choosing items by criteria (not rows) to show, export or delete them, counted and processed by the server. | [09-gui-user-guide.md](functional/09-gui-user-guide.md) |
| **Catalogue** | A provider's list of its own cloud products and services. | [02-data-collection.md](functional/02-data-collection.md) |
| **Categories cascade** | The order in which an item gets its categories: person, label links, rules, delivery method, language model, `other`. The first answer wins. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **Category / domain** | The two levels of the unified taxonomy, Domain > Category (29 domains, 224 nodes). | [04-categories.md](functional/04-categories.md) |
| **Clustered bootstrap** | Resampling whole providers to get confidence intervals that respect repeated observations of one provider. | [16-analytics.md](technical/16-analytics.md) |
| **Concept (service concept)** | A group of equivalent services of several providers ("Managed Kubernetes"), made by the language model or a person. | [06-service-correspondences.md](functional/06-service-correspondences.md) |
| **Correspondence class** | How many services of one provider match one of another inside a concept: 1:1, 2:1, 3:1, n:1. | [06-service-correspondences.md](functional/06-service-correspondences.md) |
| **Coverage matrix** | For each pair of providers, the share of one's services with an equivalent at the other. | [06-service-correspondences.md](functional/06-service-correspondences.md) |
| **Crawl** | One run of one crawler over one dataset, recorded in `crawls` with its status and counters. | [13-storage.md](technical/13-storage.md) |
| **Crawl delay** | The wait between two requests to one website: the crawler's `download_delay` (1 s by default) or the site's `Crawl-delay`, whichever is larger. | [12-crawler-framework.md](technical/12-crawler-framework.md) |
| **`CRAWLER_SOURCE`** | The environment variable choosing what a run does: catalogue, marketplace, both, statistics, reclassify, import-json, translate, correspond, metrics. | [11-configuration.md](technical/11-configuration.md) |
| **Dataset** | What one crawler writes: a provider's catalogue, a provider's marketplace, or a statistics source. Its state is in `datasets`. | [13-storage.md](technical/13-storage.md) |
| **Delivery method** | How a marketplace software is delivered: SaaS, virtual machine, container, Kubernetes, API, AI model, one-click app… | [04-categories.md](functional/04-categories.md) |
| **Derived metric** | A provider measure computed from the crawled data (products, shares, launches, parity…). | [16-analytics.md](technical/16-analytics.md) |
| **Driver analysis (rise drivers)** | The statistical ranking of the criteria that weigh most in the rise of a provider. | [08-rise-drivers.md](functional/08-rise-drivers.md) |
| **Facet (small multiples)** | One small chart per provider, bloc, domain… sharing the series, colours and time axis. | [09-gui-user-guide.md](functional/09-gui-user-guide.md) |
| **Fingerprint** | A BLAKE2b hash of an item's content (dates excluded). A change means the item was updated. | [13-storage.md](technical/13-storage.md) |
| **Forecast** | A least-squares trend over the last 8 points, projected 4 steps; log-linear for compounding sizes. A trend, not a prediction. | [16-analytics.md](technical/16-analytics.md) |
| **Generation (paged table)** | A counter changing with each query or refresh, so that late pages of an older query are ignored. | [18-gui-architecture.md](technical/18-gui-architecture.md) |
| **Granger test** | A test of whether past values of a criterion help predict the target beyond its own past. | [16-analytics.md](technical/16-analytics.md) |
| **Label seed** | `label-seed.yaml`: the known Russian and Chinese labels, translated and linked, and the noise labels. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **Label status** | `pending`, `translated`, `reviewed` or `noise`. A pending label waits for its English name. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **LLM budget** | The cost ceiling of the language model calls (10 USD by default), checked against `llm_usage` before each batch. | [15-llm-layer.md](technical/15-llm-layer.md) |
| **Marketplace** | A provider's store of third-party software (or, for five providers, its one-click applications). | [02-data-collection.md](functional/02-data-collection.md) |
| **Match key** | How a crawled item is recognized among the stored ones: its page address first, then its name (and publisher for software). Stored as 16-byte hashes. | [03-history-and-versions.md](functional/03-history-and-versions.md) |
| **Methodology break** | Synergy's Q3 2024 reclassification, which makes the shares before and after not comparable. | [07-market-statistics.md](functional/07-market-statistics.md) |
| **Mention** | A provider Synergy names, or ranks, without giving its share. | [17-statistics-crawler.md](technical/17-statistics-crawler.md) |
| **Noise label** | A provider category that says nothing ("Products", "其他"), ignored by the classifier. | [04-categories.md](functional/04-categories.md) |
| **Others (computed)** | 100 % minus the named shares of a Synergy report, computed for display, never stored. | [07-market-statistics.md](functional/07-market-statistics.md) |
| **Panel / cross-section** | The two scopes of the driver analysis: every provider × quarter with a lag, or one row per provider at its latest quarter. | [16-analytics.md](technical/16-analytics.md) |
| **Parity** | The share of a provider's products with an equivalent at AWS, Azure or Google Cloud. | [16-analytics.md](technical/16-analytics.md) |
| **Partial crawl** | A crawl finding less than half of the items listed before. Nothing is marked deleted after it. | [03-history-and-versions.md](functional/03-history-and-versions.md) |
| **Partial member** | A service matching only part of a concept, drawn dashed. | [06-service-correspondences.md](functional/06-service-correspondences.md) |
| **Preset (view)** | A ready-made chart of the "Views" menu (23, in competitive, forecast and geopolitics families). | [16-analytics.md](technical/16-analytics.md) |
| **Profile (LLM)** | A model tier of `llm.yaml`: `precise` (Opus), `balanced` (Sonnet), `fast` (Haiku). Each task is routed to one. | [15-llm-layer.md](technical/15-llm-layer.md) |
| **Progressive storage** | A running crawl writes its new and changed items every 10 s or every 2,000 items. | [13-storage.md](technical/13-storage.md) |
| **Provider** | One of the 32 cloud providers crawled (`CloudProvider`), with its country and bloc. | [01-overview.md](functional/01-overview.md) |
| **Provider metric** | One value per provider, quarter, metric and source in `provider_metrics`. | [16-analytics.md](technical/16-analytics.md) |
| **Revision** | A number from the `item_revision` sequence, bumped by every write. The GUI polls the dataset revisions to refresh. | [18-gui-architecture.md](technical/18-gui-architecture.md) |
| **robots.txt** | The website's crawling rules, obeyed everywhere, including `Crawl-delay`. See [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309). | [12-crawler-framework.md](technical/12-crawler-framework.md) |
| **Rules (classification)** | `classification.yaml`: well-known names, label rules and keywords in English, Russian and Chinese. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **Seed hash** | A SHA-256 of the three seed files. The seed is applied again only when it changes. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **Shapley / LMG split** | Sharing a regression's R² between the criteria, averaged over every order of entry. | [16-analytics.md](technical/16-analytics.md) |
| **Source label** | A category exactly as a provider writes it, in any language, stored once per normalized key. | [04-categories.md](functional/04-categories.md) |
| **Spearman correlation** | A rank correlation, robust to outliers and to the scale of the criteria. | [16-analytics.md](technical/16-analytics.md) |
| **Stealth browser** | Scrapling's Patchright-based Chromium session, for pages that need JavaScript or face anti-bot checks. | [12-crawler-framework.md](technical/12-crawler-framework.md) |
| **Storage loop** | The GUI's dedicated asyncio thread running every database job. | [18-gui-architecture.md](technical/18-gui-architecture.md) |
| **Synergy Research Group** | The market research firm whose press releases give the cloud market shares. | [17-statistics-crawler.md](technical/17-statistics-crawler.md) |
| **Umbrella category** | A broad category (storage, database, security…) dropped when a more specific category of its domain applies. | [14-classification-engine.md](technical/14-classification-engine.md) |
| **Version** | The content of an item stored for each crawl that found it new or changed (`product_versions`, `software_versions`). | [03-history-and-versions.md](functional/03-history-and-versions.md) |
| **Website date / crawl date** | Where a history date comes from: published by the provider, or observed by a crawl. | [03-history-and-versions.md](functional/03-history-and-versions.md) |

[← Docs index](README.md)
