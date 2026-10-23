[↑ Docs index](../README.md)

# What drives the rise of a cloud provider

This guide explains how to find which criteria weigh most in the rise of a cloud provider, using the data the
crawler gathers. It covers:
- which targets to explain;
- which criteria we already have, which are missing, and where to find the missing ones;
- which statistical methods to use, in which order, and the traps to avoid.

The "Rise drivers" section of the Analysis tab implements the method described here (section 7), and section 8
gives what it finds on the data crawled so far. For the longer view, who led each segment of computing since 1964
and which events changed it, see [Leaders of digital infrastructure](leaders-chronology.md).

## 1. What we can and cannot do today

| Data | Coverage | Usable for |
|---|---|---|
| Synergy Research Group market shares | **AWS, Azure, GCP only**, 22 quarters (2021Q1 to 2026Q2), whole percents, methodology break in 2024Q3 | economic target, 3 providers |
| Synergy world market size | 22 quarters | revenue = share × market size |
| Synergy Europe | 4 points (European providers aggregate, SAP, Deutsche Telekom) | context only |
| Synergy mentions | ~35 players named without share (Oracle, Huawei, CoreWeave…) | visibility criterion |
| Catalogue products | 31 providers, 3,345 products, **one snapshot** | cross-section |
| Product dates (`added_at`) | AWS (2004 to 2026) and Scaleway only | launch velocity, 2 providers |
| Marketplace software | 26 providers, 110k listings, **one snapshot** | cross-section |
| Listing dates | AWS, Azure, Oracle, Yandex (and a few small ones) | marketplace growth, 4 providers |
| Prices | **empty** (`pricing_policy`) | nothing yet |
| Service correspondences | **empty** until the AI matching runs | parity criterion, later |

Consequences:
- A regression on market share alone is impossible: 3 providers cannot separate the effect of a criterion from the
  identity of the provider.
- A **cross-section of 31 providers** on the ecosystem proxies is possible now.
- A **panel** (provider × quarter) needs history: run the catalogue and marketplace crawls every week from now
  on. After 2 to 4 quarters, every crawl adds a dated point for every provider.
- The **economic target for the other providers** needs revenue from annual reports or analysts (section 4).

## 2. Targets: what "rise" means

Two families, analysed side by side.

**Economic rise** (the market's verdict):
- market share `s(p, t)` (Synergy);
- cloud revenue `R(p, t) = s(p, t) × M(t)` (Synergy market size), or the revenue an annual report publishes;
- growth: `g(p, t) = log R(p, t) − log R(p, t − 4)` (year-on-year, removes seasonality).

**Ecosystem rise** (the provider's investment and attractiveness):
- new services per quarter (catalogue launches);
- new listings and new publishers per quarter (marketplace);
- taxonomy breadth: domains and categories covered, and their growth.

Comparing the two tells whether a criterion moves the market, the ecosystem, or both.

## 3. Criteria already gathered

| Family | Variables to build | Where they come from |
|---|---|---|
| Geography | bloc and country (dummies), home-market size | `CloudProvider.country`, `.bloc` |
| Offer breadth | products, domains, categories, umbrella against specific categories | products, `taxonomy_nodes` |
| Offer mix | share of AI/ML, data, security, compute services, audience mix (developer tools, end-user software) | `service_domains`, `categories` |
| Launch velocity | services added per quarter, deleted per quarter (churn) | `added_at`, `deleted_at` |
| Ecosystem | marketplace size, publishers, publisher overlap with AWS/Azure/GCP, delivery mix (SaaS, VM, AI model) | software, the overlap matrix |
| Parity | share of services with an equivalent at AWS/Azure/GCP, unique services | correspondences (after the AI matching) |
| Visibility | Synergy mentions and rank per quarter | `market_reports.mentions` |

Build sizes as logarithms (`log(1 + x)`), mixes as shares (0 to 1), and growth as differences of logarithms.

## 4. Criteria missing, and where to find them

| Criterion | Why it may matter | Where to find it |
|---|---|---|
| Cloud revenue, operating margin | the economic target beyond the big three | the segment notes of the 10-Q and 10-K filings (AWS, Microsoft Intelligent Cloud, Google Cloud, Oracle, IBM): **not** in the EDGAR `companyfacts` API, which holds the facts without dimension, so typed in `manual-metrics.yaml` or parsed from the filing XBRL; annual reports on HKEX and SSE (Alibaba Cloud, Tencent Cloud, Baidu AI Cloud, Kingsoft Cloud); Euronext reports (OVHcloud); Canalys, IDC and Gartner press releases (China and Europe shares) |
| Capex, data-centre investment | capacity comes before share | **collected**: EDGAR XBRL `companyfacts` (`PaymentsToAcquirePropertyPlantAndEquipment`, then `PaymentsToAcquireProductiveAssets`), the group's (Amazon, not AWS alone); annual reports for the others |
| Regions, availability zones, countries served | proximity, latency, sovereignty | the providers' region pages (stable, crawlable), PeeringDB facilities |
| Network reach | interconnection | **collected**: PeeringDB API (internet exchanges, facilities of the provider's ASNs); CAIDA AS Rank |
| AI compute | the main driver since 2023 | Epoch AI GPU clusters dataset (CSV), TOP500 lists, MLPerf results |
| Prices | price competitiveness | AWS Price List API, **Azure Retail Prices API** (no key), GCP Cloud Billing Catalog API (key), Infracost pricing database; or fill our `pricing_policy` |
| Certifications, sovereignty | public-sector and regulated demand | FedRAMP marketplace (JSON), ANSSI SecNumCloud list, BSI C5 attestations, Gaia-X labels, CSA STAR registry |
| Developer adoption | bottom-up demand | **collected**: GitHub API (stars and contributors of the SDKs and Terraform providers), Terraform Registry downloads, PyPI statistics (pypistats), Stack Exchange API (questions per tag) |
| Talent | skills supply and demand | job postings (Adzuna API, or the job scrapers of mega-trends) |
| Search interest | awareness | Google Trends (the mega-trends scraper, with its proxy settings) |
| Company facts | age, size, parent group | **collected**: Wikidata entity documents (inception, employees); parent organization and headquarters to add |
| Macro and policy | demand context and shocks | World Bank and OECD APIs (GDP, ICT spending); policy events (sanctions, EU Data Act, the mega-trends policy-shock catalogue) |
| Reliability | trust | incident history of the status pages (crawlable) |

Priority: revenue (it unlocks the economic target), then regions and capex, AI compute, developer adoption and
certifications. Every value is stored with its source and its URL, so that a result can be traced back.

## 5. Method, step by step

### Step 1: one panel table
One row per provider × quarter × criterion (long format), with its source. The cross-section is the latest
quarter, and the panel uses every quarter.

### Step 2: correlations
- **Spearman** rank correlation rather than Pearson: robust to outliers and to the huge size gap (Azure lists
  75k items, Gcore 8).
- **95% confidence intervals** by bootstrap (resampling the providers).
- **Benjamini-Hochberg q-values**: testing 30 criteria at once produces false positives otherwise.
- **Partial correlations** controlling for size and bloc. Size inflates everything (products, listings,
  publishers): a criterion matters only if it keeps a correlation once size is held constant.

### Step 3: cross-section regression (31 providers)
- Standardize every variable (mean 0, standard deviation 1): the coefficients become comparable.
- Ordinary least squares with **at most 3 predictors** (about N / 10), or ridge / elastic net beyond that.
- Judge it by the **leave-one-out R²** (each provider predicted by a model fitted without it), not the in-sample R².

### Step 4: which criteria are predominant
The **Shapley (LMG) decomposition of R²** splits the explained variance between the criteria, averaging over every
order in which they can enter the model. It is fair to correlated criteria, and it sums to the R². Bootstrap it
for intervals. This ranking is the direct answer to "which criteria are predominant".

### Step 5: panel regression (once history exists)
- **Fixed effects** (within estimator): `Δlog y(p, t) = Σ β_k Δlog x_k(p, t − L) + α_p + δ_t + ε`. The provider
  effect `α_p` removes everything constant per provider (brand, country, age), and the quarter effect `δ_t`
  removes the market-wide trend.
- Lags `L` of 1 to 4 quarters: an investment shows in share later.
- **Granger tests**: do launches precede growth, or follow it? This separates a driver from a consequence.

### Step 6: traps
| Trap | What to do |
|---|---|
| 3 providers with shares | never regress share alone, use revenue from section 4 |
| Reverse causality (leaders list more) | lags and Granger tests |
| Collinearity (size everywhere) | partial correlations, ridge, Shapley decomposition |
| Synergy rounding to whole percents, 2024Q3 methodology break | growth over 4 quarters, a break dummy |
| Year-only dates (AWS products) | yearly buckets for those providers |
| China and Russia as separate markets | bloc fixed effects, or separate runs |
| Spurious trends | always differences against differences, never levels against levels |
| Survivorship (only living providers are crawled) | keep deleted items, note the providers which stopped |

## 6. Start now
1. **Schedule weekly crawls** of every catalogue and marketplace: the history the panel needs.
2. **Run the AI matching** (`CRAWLER_SOURCE=correspond`, with `ANTHROPIC_API_KEY`) to get the parity criterion.
3. **Collect revenue** first (EDGAR for the US providers, annual reports for the others), then the other missing
   criteria in the order of section 4.
4. Run the "Rise drivers" analysis on the 31 providers (ecosystem targets), then on the economic target as revenue
   arrives.

### Stock values of the providers

The markets crawl (`CRAWLER_SOURCE=markets`, [market-shares-and-stocks.md](market-shares-and-stocks.md)) writes two
more measures per provider and quarter, source `gfinance`: `stock-value`, the quarter-end close of its listing in US
dollars, and `stock-return`, the quarterly log return. A provider takes its company's primary listing, so AWS trades
as Amazon and Azure as Microsoft: the value is the group's. They give the panel decades of quarters.

## 7. In the application

1. `CRAWLER_SOURCE=metrics uv run python src/main.py` computes the measures of every provider from the stored
   datasets (`derived` and `synergy` sources), reads `src/conf/metrics/manual-metrics.yaml` again, then crawls the
   metric sources (below): the crawlers of `src/crawler/metrics/` stream the facts as published, and
   `src/analytics/metrics/` computes them into provider metrics. The GUI computes the derived measures again before
   a run once a dataset was written, and keeps the crawled ones.

   | Source | Metrics | Coverage (2026-10-20) |
   |---|---|---|
   | SEC EDGAR `companyfacts` | capex per quarter (group, USD bn), derived from the year-to-date facts | Amazon, Microsoft, Alphabet, Oracle, IBM: 321 quarters |
   | Wikidata entity documents (`Special:EntityData`, the SPARQL endpoint is closed to crawlers) | age, employees (dated when Wikidata dates them) | 21 items |
   | PeeringDB | internet exchanges, interconnection facilities | 17 networks |
   | GitHub | stars of the Terraform provider repositories | 20 providers |

   Where each provider is found (CIK, Wikidata item, ASNs, repositories) is in `src/conf/metrics/collectors.yaml`.
   SEC EDGAR asks for a user agent naming a contact: set `CRAWLER_SEC_USER_AGENT` (e.g. `Name admin@company.example`).
   GitHub allows 60 requests an hour without `GITHUB_TOKEN`. PeeringDB throttles anonymous queries (HTTP 429): set
   `PEERINGDB_API_KEY` for regular runs. A source yielding nothing is skipped, and its stored values are kept.
2. Values found by hand (revenue from an annual report, a share from an analyst press release) go in
   `manual-metrics.yaml`, one entry per provider, quarter and metric, with the URL they were read at. A manual value
   wins over every other source.
3. Analysis tab, "Rise drivers": pick a target, the criteria, optional controls, "Latest quarter" (cross-section)
   or "Every quarter (panel)" with a lag, then Run.

| Card | What to read |
|---|---|
| Correlations | bar = Spearman ρ, whisker = 95% bootstrap interval, diamond = partial ρ (controls held constant), `*` q < 5%, `**` q < 1%; grey bars are not significant |
| Predominance | the share of the R² each criterion carries (Shapley), with its interval: the answer to "which criteria are predominant" |
| Scatter | the target against the predominant criterion, a dot per provider (or provider and quarter) |
| Table | every figure: share of R², standardized β and its interval, p-values, ρ, q, partial ρ, N, Granger p (panel) |
| Warnings | few providers measuring the target, too many criteria for the observations, collinear or constant criteria, criteria left out |

"Export CSV" saves the observations of the last run (transformed values) for another tool.

The analysis drops what it cannot use instead of shrinking the sample:
- A criterion measured for too few providers, or constant, is left out of the regression (and named in the warnings).
- Up to 7 observations, the p-value of a correlation is exact (every order of the target), since the t
  approximation would call 3 perfectly ranked providers significant.
- No bootstrap interval is drawn from fewer than 3 providers.

## 8. First findings (dev data, 2026-10-20)

Data: one catalogue snapshot of 31 providers and one marketplace snapshot of 26 providers. Synergy shares exist for
AWS, Azure and GCP only. Dated launches exist for 2 providers, and dated listings for 10. 400 bootstrap resamples.
These are **cross-section associations, not causes**: a large ecosystem may well attract a broad catalogue, rather
than the reverse.

**Marketplace size** (log of the listings, 26 providers):
| Criterion | Spearman ρ [95% CI] | q | Partial ρ (catalogue size held constant) |
|---|---|---|---|
| Categories covered | +0.70 [+0.37, +0.89] | 0.0004 | **+0.66** |
| Domains covered | +0.64 [+0.30, +0.84] | 0.002 | |
| Catalogue size (products) | +0.60 [+0.25, +0.81] | 0.004 | |
| Share of compute services | -0.45 [-0.71, -0.12] | 0.05 | -0.08 |
| Share of data services | +0.42 [-0.02, +0.70] | 0.05 | **+0.46** |
| Share of AI services | +0.40 [+0.04, +0.62] | 0.06 | +0.16 |

- **Breadth of the offer is the predominant criterion.** The categories carry 0.37 of an R² of 0.55, about two
  thirds of the explained variance, with β +0.74 (p 0.002), once the catalogue size is held constant. The size alone
  adds little once the breadth is known: the products, domains and categories are collinear, and the Shapley split
  shares them out between them.
- **Compute-heavy providers have smaller marketplaces, but only because they are small.** The negative ρ of the
  compute share vanishes once size is held constant (partial -0.08).
- **The data services keep an effect beyond size** (partial +0.46). This is the second candidate driver to watch.
- Leave-one-out R²: 0.30 to 0.38. The model predicts a provider it has not seen only moderately.

**Marketplace publishers** (26 providers): breadth again (domains ρ +0.72, products +0.68, q < 0.001). Among the
delivery modes, a large SaaS share goes with more publishers beyond size (partial +0.28, β p 0.02). The leave-one-out
R² is only 0.06, though: a weak signal.

**Catalogue size** (31 providers): larger catalogues hold a larger share of AI services (ρ +0.47, q 0.04) and a
smaller share of compute (ρ -0.41, q 0.05). The leave-one-out R² of 0.10 says the mix explains little of the size.

**Economic rise: no conclusion yet.**
- Market share: with 3 providers, products rank them perfectly (ρ +1), yet the exact p-value is 0.33, so this is not
  evidence.
- Panel: one provider (AWS) has both dated launches and dated listings, so no fixed effects regression can run.
- What unlocks both is revenue for the other providers (section 4, EDGAR first) and weekly crawls (section 6).

**With the collected criteria** (second run, same day):

| Target | Criteria | N | R² | LOO R² | Predominant (share of R²) |
|---|---|---|---|---|---|
| Marketplace size | categories, SDK stars, internet exchanges (catalogue size held constant) | 14 | 0.84 | 0.68 | **SDK stars 0.51** (60% of R²), β +0.98, p 0.002 |
| Publishers | domains, SDK stars, internet exchanges, age | 10 | 0.96 | 0.75 | **SDK stars 0.58** (60% of R²), β +1.13, p 0.002 |
| Catalogue size | SDK stars, internet exchanges, age | 10 | 0.70 | -0.43 | SDK stars 0.59, but the model does not predict a new provider |

- **Developer adoption is the strongest criterion found so far.** The GitHub stars of a provider's Terraform
  provider correlate with its marketplace size (ρ +0.63, q 0.004), even with the catalogue size held constant
  (partial +0.43). Once the stars are in the regression, the breadth of the catalogue adds nothing (β -0.08): breadth
  and adoption go together, and adoption carries the explanation.
- **Network reach** (internet exchanges) correlates (ρ +0.61), but adds nothing beyond adoption and breadth.
- **Age does not matter** (ρ -0.30, not significant): younger providers are not smaller.
- **Economic panel** (AWS, Azure, Google Cloud, 38 provider-quarters, yearly changes, provider and quarter
  effects). Capex growth two quarters earlier explains 15% of the within variance of revenue growth (β +0.39,
  p 0.07). The same quarter explains 4%, and four quarters earlier 3%. Capex does not lead revenue in the Granger
  test (p 0.70). The capex is the group's (Amazon's includes its retail warehouses), and 3 providers remain too few:
  an indication, not a finding.

**What to do next:**
1. Type the cloud segment revenue in `manual-metrics.yaml` (AWS, Microsoft Intelligent Cloud, Google Cloud, Oracle,
   Alibaba Cloud, Tencent, OVHcloud annual reports). The Analysis tab then answers on the economic target for more
   than 3 providers (`cloud-revenue`).
2. Fill the gaps of the metric crawlers: the regions (provider region pages), the certifications (FedRAMP, SecNumCloud,
   C5), GitHub stars of the SDKs, and Wikidata items for the providers that have none.
3. Re-run on a panel once 4 or more quarters of crawls exist. Panel results are within-provider, which takes out
   most of the reverse causality of these cross-section results.
