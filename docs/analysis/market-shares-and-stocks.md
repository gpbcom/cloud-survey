# Market shares and stock values of the leaders

The leaders chronology ([leaders-chronology.md](leaders-chronology.md)) says who led each segment of computing since 1964. This guide covers the evolution behind it: the **market share** of each company over time, worldwide and by area, and the **stock value** of its listings, in their own currency or converted. It also covers how the two are correlated.

The data come from `CRAWLER_SOURCE=markets`. The Analysis tab shows them in three cards, under the leaders: "Market shares", "Stock values" and "Share vs stock".

## 1. Sources

Retrieved on 2026-10-23. Every stored row keeps its source and its document (`source`, `source_url`), and every tooltip names its source.

| Source | What it measures | Unit | Granularity and span | Areas | Terms | robots.txt |
|---|---|---|---|---|---|---|
| [StatCounter Global Stats](https://gs.statcounter.com/) (`chart.php?…&csv=1`) | Usage share of search engines, browsers, operating systems, device vendors, AI chatbots | % of the page views of a panel of about 1.5 million sites | Monthly, from 2009-01 (vendors from 2010-04, AI chatbots from 2025-04) | World, 6 continents, every country (ISO alpha-2) | Free to reuse with attribution, CC BY-SA 3.0 | None (404): crawled at one request every 2 s |
| [Synergy Research Group](https://www.srgresearch.com/) press releases (statistics crawl) | Share of cloud infrastructure services revenue (IaaS, PaaS, hosted private cloud) | % of revenue | Quarterly, from the releases crawled | Worldwide, Europe | Press releases, quoted with their link | Obeyed by the statistics crawl |
| [Google Finance](https://www.google.com/finance/) chart RPC (`batchexecute`, `c2u4wc`, window 8 = Max) | Weekly closing price of each listing | Listing currency, split-adjusted, dividends not reinvested | Weekly, over the listing's history (IBM, Microsoft, Intel from 1986) | Every exchange Google lists | Google's terms: "for informational purposes", no redistribution of the raw feed | `/finance/` allowed (only `/m/finance` mentioned) |
| [FRED](https://fred.stlouisfed.org/) (`fredgraph.csv`) | Noon buying rates in New York (H.10) of 13 currencies against the US dollar, and the OECD monthly rouble rate | Units per dollar or dollars per unit | Daily from 1971 (euro from 1999), rouble monthly from 1992 | - | Public data, no key | Allowed (`Crawl-delay: 1`) |
| [World Bank API](https://api.worldbank.org/v2/) | Internet users (`IT.NET.USER.ZS`) and population (`SP.POP.TOTL`) of the EU member states | % and people | Yearly from 2008 | The 27 member states | CC BY 4.0 | None (404) |
| [TrendForce press center](https://www.trendforce.com/presscenter/news/Semiconductors) | Share of revenue of the top foundries, DRAM and NAND suppliers, read from the release sentences ("capturing a 72.5% market share") | % of revenue | Quarterly (some years), releases back to 2008; the smaller companies are often unnamed | Worldwide | Press releases, quoted with their link | Allowed (only `/api`, `/search`, `/research/feedback` disallowed) |
| [IDC press releases](https://www.idc.com/resource-center/press-releases/) (WordPress API `wp-json/wp/v2/press-release`) | Share of unit shipments of the top 5 PC, smartphone and tablet makers, from the release tables (current and year-ago quarter) | % of sell-in units | Quarterly (some yearly), from 2021 (the current site starts in September 2022) | Worldwide, India, China, Japan, Indonesia, Thailand, Vietnam, the Philippines | Press releases, quoted with their link | Allowed (`Disallow:` empty) |
| [Source dossier](sources/computing-leaders-1964-2026.md), Tabs 1 and 3 | Pre-2009 shares (IBM, IBM PC, Nokia, Symbian…) and IPOs, acquisitions, private rounds, market caps of the companies without a price history | % and USD bn | Sourced dates, 1991 to 2026 | - | Each point tagged P (primary filing), J (journalistic), B (blog or aggregator) | - |

Sources not used, and why:
- **Stooq and Yahoo Finance** chart APIs: their `robots.txt` disallow every crawler, and the crawlers obey `robots.txt`.
- **The ECB reference rates** (`eurofxref-hist.zip`): they start in 1999 and have no Taiwan dollar. FRED covers the same currencies from 1971, with the dollar as the pivot.
- **Gartner** newsroom: a Cloudflare challenge answers every request (HTTP 403). It is not worked around.
- **Canalys** (now part of Omdia): the newsroom answers HTTP 403, and its sitemap stops in 2021.
- **Jon Peddie Research**: the GPU shares are only in chart images, the text gives their changes ("Nvidia's share decreased by 0.1%"), and its API is behind a Cloudflare challenge.
- **Counterpoint**: its `robots.txt` only names AI search agents.
- **Before 2009** no crawlable source exists: the dossier's points are typed in the catalogue (phase 3, section 3).

## 2. What is crawled

`conf/history/markets.yaml` lists what is read: the segments, the areas, the company behind each source label, the currencies, the listings and the valuation points. Every company is a company of the chronology (its name, colour and country of headquarters come from `conf/history/chronology.yaml`). The block below is printed from the YAML by `uv run render-markets-doc` (a test checks it is up to date).

<!-- markets:catalogue:start -->
### Segments

| Segment | Source | Statistic | Devices (default first) | From | Definition |
|---|---|---|---|---|---|
| Web search | statcounter | search_engine | all, desktop, mobile, tablet | 2009-01 | Share of the search referrals to the 1.5 million sites of the StatCounter panel (page views, not users or revenue). |
| Web browsers | statcounter | browser | all, desktop, mobile, tablet | 2009-01 | Share of the page views of the StatCounter panel, by browser. |
| Operating systems | statcounter | os_combined | mobile, all, desktop, tablet | 2009-01 | Share of the page views of the StatCounter panel, by operating system (on phones: the smartphone OS). |
| Device vendors | statcounter | vendor | mobile, tablet, all | 2009-01 | Share of the page views of the StatCounter panel, by phone or tablet vendor (installed base in use, not shipments). |
| AI chatbots | statcounter | ai_chatbot | all, desktop, mobile, tablet | 2025-04 | Share of the referrals from AI chatbots to the StatCounter panel (from April 2025). |
| Cloud infrastructure | synergy | - | all | - | Share of cloud infrastructure services revenue (IaaS, PaaS, hosted private cloud), Synergy Research Group, quarterly. |
| Chip foundry | trendforce | - | all | - | Share of the revenue of the top 10 foundries, TrendForce, quarterly (the pure-play and IDM foundry businesses). |
| DRAM | trendforce | - | all | - | Share of DRAM revenue by supplier, TrendForce, quarterly. |
| NAND flash | trendforce | - | all | - | Share of NAND flash revenue by supplier, TrendForce, quarterly. |
| PCs | idc | - | all | - | Share of traditional PC shipments (desktops, notebooks, workstations; sell-in), IDC, quarterly. |
| Smartphones | idc | - | all | - | Share of smartphone shipments (sell-in), IDC, quarterly. |
| Tablets | idc | - | all | - | Share of tablet shipments (sell-in), IDC, quarterly. |
| Mainframes & EDP industry | manual | - | all | - | IBM's share of the US electronic data processing industry revenue (as defined in US v. IBM), of mainframe sales, and of computers worldwide (dossier points, 1961 to 1985). |
| x86 CPUs | manual | - | all | - | x86 processor unit shipments, PC and server (Mercury Research, dossier points). |
| Smartphone OS (sales) | manual | - | all | - | Smartphone operating systems, sales to end users (Gartner, dossier points); StatCounter's operating systems are page views. |

### Areas

1 world, 6 continents, 1 union and 64 countries.

- **Countries:** United States (US), United Kingdom (GB), Germany (DE), France (FR), Italy (IT), Spain (ES), Netherlands (NL), Poland (PL), Sweden (SE), Belgium (BE), Austria (AT), Ireland (IE), Denmark (DK), Finland (FI), Portugal (PT), Czechia (CZ), Greece (GR), Hungary (HU), Romania (RO), Bulgaria (BG), Croatia (HR), Slovakia (SK), Slovenia (SI), Lithuania (LT), Latvia (LV), Estonia (EE), Luxembourg (LU), Cyprus (CY), Malta (MT), Switzerland (CH), Norway (NO), Ukraine (UA), Turkey (TR), Russia (RU), Canada (CA), Mexico (MX), Brazil (BR), Argentina (AR), Chile (CL), Colombia (CO), China (CN), Japan (JP), South Korea (KR), Taiwan (TW), Hong Kong (HK), India (IN), Indonesia (ID), Vietnam (VN), Thailand (TH), Philippines (PH), Malaysia (MY), Singapore (SG), Pakistan (PK), Bangladesh (BD), Israel (IL), Saudi Arabia (SA), United Arab Emirates (AE), Egypt (EG), Nigeria (NG), Kenya (KE), South Africa (ZA), Morocco (MA), Australia (AU), New Zealand (NZ).
- **Unions (estimated from their members):** EU-27 (estimate): AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT, LV, LT, LU, MT, NL, PL, PT, RO, SK, SI, ES, SE.

### Listings

| Company | Listing | Currency | Primary | Note |
|---|---|---|---|---|
| IBM | NYSE:IBM | USD | yes |  |
| Microsoft | NASDAQ:MSFT | USD | yes |  |
| Oracle | NYSE:ORCL | USD | yes |  |
| Apple | NASDAQ:AAPL | USD | yes |  |
| HP | NYSE:HPQ | USD | yes | HP Inc. (Hewlett-Packard until the 2015 split) |
| HP | NYSE:HPE | USD | no | Hewlett Packard Enterprise (from the 2015 split) |
| Lenovo | HKG:0992 | HKD | yes |  |
| Intel | NASDAQ:INTC | USD | yes |  |
| AMD | NASDAQ:AMD | USD | yes |  |
| Cisco | NASDAQ:CSCO | USD | yes |  |
| Google | NASDAQ:GOOGL | USD | yes | Alphabet (Google until 2015) |
| Nokia (Symbian) | HEL:NOKIA | EUR | yes |  |
| Nokia (Symbian) | NYSE:NOK | USD | no | ADR |
| TSMC | TPE:2330 | TWD | yes |  |
| TSMC | NYSE:TSM | USD | no | ADR |
| Nvidia | NASDAQ:NVDA | USD | yes |  |
| Amazon (AWS) | NASDAQ:AMZN | USD | yes | Amazon, parent of AWS |
| AT&T | NYSE:T | USD | yes |  |
| Unisys (Burroughs, Sperry) | NYSE:UIS | USD | yes |  |
| Verizon | NYSE:VZ | USD | yes |  |
| SMIC | HKG:0981 | HKD | yes |  |
| SMIC | SHA:688981 | CNY | no | Shanghai STAR Market |
| Arm | NASDAQ:ARM | USD | yes |  |
| Broadcom | NASDAQ:AVGO | USD | yes | Broadcom, owner of VMware since 2023 |
| CoreWeave | NASDAQ:CRWV | USD | yes |  |
| Samsung | KRX:005930 | KRW | yes |  |
| Xiaomi | HKG:1810 | HKD | yes |  |
| Motorola | NYSE:MSI | USD | yes | Motorola Solutions (Motorola until the 2011 split) |
| BlackBerry (RIM) | NYSE:BB | USD | yes |  |
| BlackBerry (RIM) | TSE:BB | CAD | no | Toronto |
| Sony | NYSE:SONY | USD | yes | ADR |
| Sony | TYO:6758 | JPY | no | Tokyo |
| LG | KRX:066570 | KRW | yes | LG Electronics |
| HTC | TPE:2498 | TWD | yes |  |
| Opera | NASDAQ:OPRA | USD | yes |  |
| Yandex | NASDAQ:NBIS | USD | yes | Nebius Group, the former Yandex N.V. (history from 2024-10 only) |
| Baidu | NASDAQ:BIDU | USD | yes | ADS |
| Baidu | HKG:9888 | HKD | no |  |
| Naver | KRX:035420 | KRW | yes |  |
| Tencent | HKG:0700 | HKD | yes |  |
| Tencent | OTCMKTS:TCEHY | USD | no | ADR |
| Alibaba | NYSE:BABA | USD | yes | ADS |
| Alibaba | HKG:9988 | HKD | no |  |
| Qihoo 360 | SHA:601360 | CNY | yes | 360 Security Technology |
| SAP | ETR:SAP | EUR | yes |  |
| SAP | NYSE:SAP | USD | no | ADR |
| OVHcloud | EPA:OVH | EUR | yes |  |
| Dell | NYSE:DELL | USD | yes | Dell Technologies (relisted 2018) |
| UMC | TPE:2303 | TWD | yes |  |
| UMC | NYSE:UMC | USD | no | ADR |
| GlobalFoundries | NASDAQ:GFS | USD | yes |  |
| Hua Hong | HKG:1347 | HKD | yes |  |
| SK hynix | KRX:000660 | KRW | yes |  |
| Micron | NASDAQ:MU | USD | yes |  |
| Kioxia | TYO:285A | JPY | yes |  |
| Western Digital | NASDAQ:WDC | USD | yes |  |
| SanDisk | NASDAQ:SNDK | USD | yes | Spun off from Western Digital in 2025 |
| Nanya | TPE:2408 | TWD | yes |  |
| Winbond | TPE:2344 | TWD | yes |  |
| ASUS | TPE:2357 | TWD | yes |  |
| Acer | TPE:2353 | TWD | yes |  |
| Transsion | SHA:688036 | CNY | yes |  |

### Valuation points

| Company | Date | Kind | USD bn | What | Source | Tag |
|---|---|---|---|---|---|---|
| Ashton-Tate | 1991-07-09 | deal | 0.44 | To Borland | DOJ Competitive Impact Statement | P |
| WordPerfect | 1994-06 | deal | 0.855 | To Novell (1.4 announced) | Deseret News | J |
| Lotus | 1995-07-05 | deal | 3.2 to 3.5 | To IBM | IBM 10-Qs | P |
| WordPerfect | 1996 | deal | 0.186 to 0.2 | To Corel | Deseret News | J |
| DEC | 1998-01-26 | deal | 9.6 | To Compaq | DEC 8-K | P |
| Netscape | 1998-11-24 | deal | 4.2 | To AOL | AOL 8-K | P |
| Compaq | 2002-05-03 | deal | 25 | To HP | HP 424B5 | P |
| Google | 2004-08-18 | ipo | 23 | IPO at $85 | Prospectus and Washington Post | P |
| IBM | 2005-05 | deal | 1.25 | PC unit to Lenovo | China Daily and Forbes | J |
| Sun Microsystems | 2010-01-27 | deal | 7.4 | To Oracle | eWeek and Oracle 10-K | P |
| Palm | 2010-04-28 | deal | 1.2 | To HP | HP and Palm release | P |
| Yahoo | 2017-06-13 | deal | 4.48 | To Verizon (from 4.83) | Verizon 10-Q | P |
| Arm | 2023-09-14 | ipo | 52.3 to 54.5 | IPO at $51 | Fortune and StoneX | J |
| VMware | 2023-11-22 | deal | 61 to 69 | To Broadcom | VMware DEF 14A | P |
| OpenAI | 2025-03 | private-round | 300 | Post-money | RevenueMemo | B |
| CoreWeave | 2025-03-27 | ipo | 19 to 23 | IPO at $40 | CoreWeave and CNBC | P |
| Anthropic | 2026-02 | private-round | 380 | Series G | Pinggy and ValueAddVC | B |
| OpenAI | 2026-03-31 | private-round | 852 | Post-money | Reuters | J |
| Anthropic | 2026-05-28 | private-round | 965 | Series H | Pinggy and ValueAddVC | B |
| TSMC | 2026-10 | market-cap | 2450 | Market cap | AlphaSense | B |
| Nvidia | 2026-10-09 | market-cap | 5536 | Market cap | finhacker.cz | B |
| Apple | 2026-10-09 | market-cap | 4918 | Market cap | finhacker.cz | B |
| Google | 2026-10-09 | market-cap | 4301 | Market cap (Alphabet) | finhacker.cz | B |
| Microsoft | 2026-10-09 | market-cap | 3974 | Market cap | finhacker.cz | B |
| Amazon (AWS) | 2026-10-09 | market-cap | 2830 | Market cap | finhacker.cz | B |
| Broadcom | 2026-10-09 | market-cap | 1726 | Market cap | finhacker.cz | B |
| AMD | 2026-10-09 | market-cap | 992 | Market cap | finhacker.cz | B |

### Press release families (phase 2)

| Firm | Segment | Area | Search | Matches (title | caption) | Excludes |
|---|---|---|---|---|---|
| idc | smartphones | IN | smartphone | `India.*smartphone\|smartphone.*India` | `used\|refurbish\|foldable\|feature phone\|wearable` |
| idc | smartphones | CN | smartphone | `China.*smartphone\|smartphone.*China` | `used\|refurbish\|foldable\|wearable` |
| idc | smartphones | JP | smartphone | `Japan.*smartphone\|smartphone.*Japan` | - |
| idc | smartphones | ID | smartphone | `Indonesia.*smartphone\|smartphone.*Indonesia` | - |
| idc | smartphones | TH | smartphone | `Thailand.*smartphone\|smartphone.*Thailand` | - |
| idc | smartphones | VN | smartphone | `Vietnam.*smartphone\|smartphone.*Vietnam` | - |
| idc | smartphones | PH | smartphone | `Philippines.*smartphone\|smartphone.*Philippines` | - |
| idc | smartphones | ww | smartphone | `smartphone` | `used\|refurbish\|foldable\|feature phone\|wearable\|AR/VR\|India\|China\|Chinese\|Japan\|Philippines\|Middle East\|Africa\|Europe\|Asia\|Canada\|Latin America\|Indonesia\|Thailand\|Vietnam\|Malaysia\|Singapore\|Korea\|Australia\|Turkey\|Saudi\|Emirates\|Brazil\|Mexico\|United States\|U\.S\.\|\bUS\b` |
| idc | pcs | IN | PC | `India.*\bPCs?\b\|\bPCs?\b.*India` | `monitor\|workstation\|chromebook\|tablet\|gaming` |
| idc | pcs | PH | PC | `Philippines.*\bPCs?\b\|\bPCs?\b.*Philippines` | `monitor\|workstation\|chromebook\|tablet\|gaming` |
| idc | pcs | ww | PC | `\bPCs?\b` | `monitor\|workstation\|chromebook\|tablet\|gaming\|peripheral\|India\|China\|Chinese\|Japan\|Philippines\|Middle East\|Africa\|Europe\|Asia\|Canada\|Latin America\|Indonesia\|Thailand\|Vietnam\|Malaysia\|Singapore\|Korea\|Australia\|Turkey\|Saudi\|Emirates\|Brazil\|Mexico\|United States\|U\.S\.\|\bUS\b` |
| idc | tablets | IN | tablet | `India.*tablet\|tablet.*India` | `chromebook` |
| idc | tablets | ww | tablet | `tablet` | `chromebook\|India\|China\|Chinese\|Japan\|Philippines\|Middle East\|Africa\|Europe\|Asia\|Canada\|Latin America\|Indonesia\|Thailand\|Vietnam\|Malaysia\|Singapore\|Korea\|Australia\|Turkey\|Saudi\|Emirates\|Brazil\|Mexico\|United States\|U\.S\.\|\bUS\b` |
| trendforce | foundry | ww | - | `foundr(y\|ies).*(revenue\|ranking\|market share)\|(revenue\|ranking\|top 10\|top ten\|top-10).*foundr(y\|ies)` | `forecast\|projected\|expected\|outlook\|will \|to reach\|to grow\|to undergo\|module\|price\|contract\|spot\|HBM\|capex\|wafer\|inventor\|shipment\|memory market revenue\|packaging\|earthquake\|outage\|capacity\|equipment` |
| trendforce | dram | ww | - | `\bDRAM\b.*(revenue\|ranking\|market share)\|(revenue\|ranking).*\bDRAM\b` | `forecast\|projected\|expected\|outlook\|will \|to reach\|to grow\|module\|price\|contract\|spot\|HBM\|mobile DRAM\|server DRAM\|enterprise SSD\|capex\|wafer\|inventor\|shipment\|NAND` |
| trendforce | nand | ww | - | `NAND.*(revenue\|ranking\|market share\|brand)\|(revenue\|ranking).*NAND` | `forecast\|projected\|expected\|outlook\|will \|to reach\|to grow\|module\|price\|contract\|spot\|HBM\|mobile DRAM\|server DRAM\|enterprise SSD\|capex\|wafer\|inventor\|shipment\|DRAM` |

### Manual share points of the dossier (phase 3)

| Segment | Area | Period | Company | Share % | Source | Tag |
|---|---|---|---|---|---|---|
| mainframes | US | 1961 | IBM | 52 | Fisher-McKie-Mancke via Cato 1985 | A |
| mainframes | US | 1968 | IBM | 50 | Fisher-McKie-Mancke via Cato 1985 | A |
| mainframes | US | 1972 | IBM | 37 | Fisher-McKie-Mancke via Cato 1985 | A |
| mainframes | US | 1981 | IBM (mainframe sales) | 69.4 | Fisher-McKie-Mancke via Cato 1985 | A |
| mainframes | US | 1982 | IBM | 37 | Fisher-McKie-Mancke via Cato 1985 (approx.) | A |
| mainframes | US | 1983 | IBM (mainframe sales) | 73.8 | Fisher-McKie-Mancke via Cato 1985 | A |
| mainframes | ww | 1976 | IBM (computers) | 50 | CMU slides | B |
| mainframes | ww | 1985 | IBM (computers) | 25 | CMU slides | B |
| pcs | ww | 1984 | IBM PC | 26 | Dataquest via transcript (weak) | B |
| pcs | ww | 2025 | Lenovo | 27.2 | Gartner | I |
| pcs | ww | 2025 | Dell | 15.3 | Gartner | I |
| pcs | ww | 2025 | Apple | 9.2 | Gartner | I |
| x86 | ww | 2026Q2 | Intel | 69.3 | Mercury Research | I |
| x86 | ww | 2026Q2 | AMD | 30.7 | Mercury Research | I |
| smartphones | ww | 2007 | Nokia | 49.4 | Gartner (sales to end users) | I |
| smartphones | ww | 2008 | Nokia | 43.7 | Gartner (sales to end users) | I |
| smartphone-os-sales | ww | 2008 | Symbian | 52.4 | Gartner | I |
| smartphone-os-sales | ww | 2009 | Symbian | 46.9 | Gartner | I |
| smartphone-os-sales | ww | 2009 | RIM | 19.9 | Gartner | I |
| smartphone-os-sales | ww | 2009 | iOS | 14.4 | Gartner | I |
| smartphone-os-sales | ww | 2009 | Android | 3.9 | Gartner | I |
| smartphone-os-sales | ww | 2009 | WebOS | 0.7 | Gartner | I |
| foundry | ww | 2024Q4 | TSMC | 67.1 | TrendForce via the dossier | I |

### Currencies (FRED, against the US dollar)

| Currency | Series | Quoted |
|---|---|---|
| EUR | DEXUSEU | usd-per-unit |
| GBP | DEXUSUK | usd-per-unit |
| JPY | DEXJPUS | units-per-usd |
| KRW | DEXKOUS | units-per-usd |
| CNY | DEXCHUS | units-per-usd |
| HKD | DEXHKUS | units-per-usd |
| TWD | DEXTAUS | units-per-usd |
| CAD | DEXCAUS | units-per-usd |
| CHF | DEXSZUS | units-per-usd |
| SEK | DEXSDUS | units-per-usd |
| NOK | DEXNOUS | units-per-usd |
| DKK | DEXDNUS | units-per-usd |
| INR | DEXINUS | units-per-usd |
| RUB | CCUSMA02RUM618N | units-per-usd |
<!-- markets:catalogue:end -->

## 3. How the figures are built

- **Labels to companies.** A StatCounter label is stored as printed and mapped to its company: `Chrome`, `Chromium`, `Android`, `Chrome OS` and `Google Gemini` are Google; `bing`, `IE`, `Edge` and `Windows` are Microsoft. A label of no company (`Linux`, `Unknown`, a small engine) goes to "Others". A chart line sums the labels of a company, and its tooltip lists them.
- **The EU-27** is not published by StatCounter. Its share is the average of the members' shares, each weighted by its internet users that year (World Bank: internet users in % × population). A member weighs in a month only if StatCounter has figures for it that month. A year the World Bank has not published yet takes the latest known year. The EU-27 lines are dashed and labelled "(est.)".
- **Press releases** (phase 2). A release is read when its title, and the caption of its table, match a family of `press` in the catalogue. The family gives the segment and the area; the countries are listed before the worldwide families, which exclude every regional wording.
  - A table is classified by its caption first ("Top Five Tablet Companies, Worldwide Shipments"). When the caption names no product ("Worldwide Shipments"), the title is read with it. Chromebooks are excluded from the PC and tablet families.
  - **IDC** tables give every share column summing to about 100% (the top 5 and Others; a column summing otherwise is partial and left out): the quarter, and the same quarter a year before. A period stated by several releases takes the shares of a single release: the one whose shares sum closest to 100% (the most complete), the latest on a tie. A crawl replaces the stored shares of the periods it writes, so a period never mixes two top 5s.
  - **TrendForce** sentences give the shares they state. A share goes to the company named last before it, or to the one named in the sentence before ("Its market share edged up to 5.4%"). The following are left out:
    - a share introduced by "the", or owned by a group or a process node ("Korean vendors' market share", "this node's revenue share"), even when a company is named earlier in the sentence;
    - a share in a sentence naming a group but no company ("these two South Korean manufacturers account for 70.8%");
    - a change ("0.5% market share growth"), and a share of 99% or more;
    - the quarters whose shares sum above 100%.
    The companies outside the chronology (Elpida, Powerchip, ProMOS…, `press_names` in the catalogue) are read under their own name, so their share never goes to the company named before. Toshiba's memory business is Kioxia, Hynix is SK hynix. A quarter written without its year takes the title's year, else the publication's.
- **Manual points** (phase 3): the shares of the source dossier no crawled source gives, the IBM era (1961 to 1985), the IBM PC (1984), Nokia and Symbian (2007 to 2009), x86 (Mercury) and Gartner's PCs. They are written at the end of every markets crawl with the source `manual`, drawn as dots. A segment's own source wins where both give a company's share for the same period.
- **Cloud shares** come from the stored Synergy reports. The aggregates (the big three, the European providers) are left out, so a quarter never counts anyone twice. They are drawn as dots, never interpolated.
- **Currencies.** A price converts on its own day, through the US dollar (FRED's rate on or just before that day, at most 40 days old). A day before a currency's first rate has no conversion: a Helsinki price of 1995 shows in euros only from 1999, and the tooltip says so.
- **Indexed scale.** Each line is rebased to 100 at its first point in the window, so listings of different currencies and sizes compare.
- **Region indexes.** These are equal-weight indexes of the primary listings of the companies headquartered in a region (United States, United Kingdom, European Union, Other Europe, China and Hong Kong, Japan, South Korea, Taiwan, Russia, Canada). They are chain-linked monthly: a listing joining (an IPO) or leaving does not make the index jump.
- **Valuation points** are drawn as dots in USD bn, never correlated: they are too sparse.

## 4. Correlation-ready data

The series must support correlations, between shares and stock values and with the Rise drivers criteria:

- **One time step: the month.** StatCounter is monthly: about 214 points per series from 2009-01 to 2026-10. The stock prices are reduced to month-end closes, about 480 points for IBM, Microsoft or Intel since 1986. The quarterly sources (Synergy, TrendForce, IDC) stay quarterly and are compared with quarter-end closes, never interpolated: the "Share vs stock" card then works in quarters (lags of up to 4 quarters, at least 16 quarters, blocks of 2 quarters).
- **Thresholds.** A series is correlated with at least 36 monthly points (16 quarterly) and no gap over 3 periods. Below that, the "Share vs stock" card refuses and says why. The block of section 6 counts the points of every stored series.
- **Changes, not levels.** The share change is in points from one month to the next, and the return is the log change of the month-end close in US dollars. Two trending series always correlate in levels.
- **Lags.** At lag `k`, the share change of month `t` is paired with the return of month `t + k`. Lags run from -12 to +12. A positive lag asks whether the market follows the share, a negative one whether the share follows the market.
- **Intervals and multiple testing.** The months are autocorrelated, so the 95% intervals come from a moving-block bootstrap (blocks of 6 months, 400 resamples, fixed seed). The q-values (Benjamini-Hochberg) correct for the 25 lags tested.
- **Granger tests, both ways.** These use 3 months of past: do the share changes predict the returns beyond the returns' own past, and the other way round? A feedback loop shows small p-values in both directions. Correlation is not causation: both may follow the same cycle.
- **Rise drivers.** The month-end closes in US dollars of the providers' listings (AWS as Amazon, Azure as Microsoft, Google Cloud as Alphabet, Oracle, IBM, Alibaba, Tencent, Baidu, OVHcloud…) are written to `provider_metrics` as `stock-value` (quarter-end close) and `stock-return` (quarterly log return), source `gfinance`. They give the panel analysis decades of quarterly points ([rise-drivers.md](rise-drivers.md)).

## 5. Limits

- **Page views, not users, units or revenue.** StatCounter counts the page views of its panel. Its "Samsung" vendor share is the installed base in use, not shipments, and a search share is a share of the referrals to the panel's sites, not of queries.
- **The EU-27 is an estimate** (section 3).
- **Prices** are split-adjusted, but dividends are not reinvested: a total return would be higher for the dividend payers (IBM, AT&T, Verizon).
- **ADRs and second listings** are drawn dashed. They follow the primary listing through the exchange rate, with their own trading hours.
- **Missing histories.** Google Finance has no history for delisted companies (DEC, Sun, Compaq, Netscape, Yahoo, VMware…): they get valuation points. Yandex's Nasdaq history ends with its 2024 sale and Nebius (`NASDAQ:NBIS`) starts in October 2024. Moscow listings are not on Google Finance.
- **Subsidiaries** trade as their parent: the value of AWS is Amazon's.

## 6. Coverage of the stored series

Printed by `uv run render-markets-doc --coverage` after a crawl (it reads the database of `CRAWLER_DATABASE_URL`).

<!-- markets:coverage:start -->
Measured on 2026-10-23: 1368 monthly share series (1080 long enough to correlate), 17 quarterly share series (3 long enough) and 61 listings. A series can be correlated with at least 36 months or 16 quarters and no gap over 3.

### Market shares (months with figures)

| Segment | Area | Devices | First | Last | Months | Longest gap | Correlatable |
|---|---|---|---|---|---|---|---|
| ai-chatbots | AE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AE | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AT | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AT | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AT | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AT | tablet | 2025-04 | 2026-10 | 17 | 1 | no |
| ai-chatbots | AU | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AU | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AU | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | AU | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BD | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BD | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BD | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BD | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BE | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BG | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BG | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BG | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BG | tablet | 2025-04 | 2026-10 | 18 | 1 | no |
| ai-chatbots | BR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | BR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CA | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CA | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CA | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CA | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CH | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CH | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CH | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CH | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CL | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CL | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CL | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CL | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CN | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CN | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CN | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CN | tablet | 2025-04 | 2026-09 | 15 | 2 | no |
| ai-chatbots | CO | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CO | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CO | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CO | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CY | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CY | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CY | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CY | tablet | 2025-04 | 2026-10 | 14 | 2 | no |
| ai-chatbots | CZ | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CZ | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CZ | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | CZ | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DE | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DK | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DK | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DK | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | DK | tablet | 2025-05 | 2026-10 | 18 | 0 | no |
| ai-chatbots | EE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EE | tablet | 2025-04 | 2026-06 | 13 | 1 | no |
| ai-chatbots | EG | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EG | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EG | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | EG | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ES | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ES | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ES | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ES | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FI | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FI | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FI | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FI | tablet | 2025-04 | 2026-09 | 18 | 0 | no |
| ai-chatbots | FR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | FR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GB | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GB | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GB | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GB | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | GR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HK | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HK | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HK | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HK | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HR | tablet | 2025-04 | 2026-10 | 17 | 2 | no |
| ai-chatbots | HU | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HU | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HU | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | HU | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ID | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ID | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ID | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ID | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IE | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IL | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IL | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IL | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IL | tablet | 2025-04 | 2026-10 | 18 | 1 | no |
| ai-chatbots | IN | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IN | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IN | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IN | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IT | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IT | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IT | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | IT | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | JP | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | JP | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | JP | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | JP | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KE | tablet | 2025-04 | 2026-10 | 17 | 1 | no |
| ai-chatbots | KR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | KR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LT | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LT | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LT | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LT | tablet | 2025-04 | 2026-09 | 17 | 1 | no |
| ai-chatbots | LU | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LU | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LU | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LU | tablet | 2025-04 | 2026-05 | 11 | 2 | no |
| ai-chatbots | LV | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LV | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LV | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | LV | tablet | 2025-04 | 2026-10 | 14 | 1 | no |
| ai-chatbots | MA | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MA | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MA | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MA | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MT | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MT | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MT | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MT | tablet | 2025-04 | 2026-04 | 13 | 0 | no |
| ai-chatbots | MX | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MX | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MX | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MX | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MY | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MY | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MY | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | MY | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NG | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NG | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NG | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NG | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NL | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NL | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NL | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NL | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NO | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NO | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NO | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NO | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NZ | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NZ | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NZ | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | NZ | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PH | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PH | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PH | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PH | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PK | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PK | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PK | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PK | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PL | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PL | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PL | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PL | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PT | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PT | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PT | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | PT | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RO | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RO | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RO | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RO | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RU | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RU | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RU | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | RU | tablet | 2025-05 | 2026-07 | 13 | 1 | no |
| ai-chatbots | SA | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SA | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SA | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SA | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SE | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SE | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SE | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SE | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SG | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SG | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SG | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SG | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SI | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SI | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SI | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SI | tablet | 2025-04 | 2026-10 | 17 | 1 | no |
| ai-chatbots | SK | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SK | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SK | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | SK | tablet | 2025-04 | 2026-10 | 18 | 1 | no |
| ai-chatbots | TH | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TH | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TH | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TH | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TR | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TR | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TR | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TR | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TW | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TW | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TW | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | TW | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | UA | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | UA | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | UA | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | UA | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | US | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | US | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | US | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | US | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | VN | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | VN | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | VN | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | VN | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ZA | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ZA | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ZA | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ZA | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | af | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | af | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | af | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | af | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | as | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | as | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | as | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | as | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu27 | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu27 | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu27 | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | eu27 | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | na | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | na | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | na | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | na | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | oc | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | oc | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | oc | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | oc | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | sa | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | sa | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | sa | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | sa | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ww | all | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ww | desktop | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ww | mobile | 2025-04 | 2026-10 | 19 | 0 | no |
| ai-chatbots | ww | tablet | 2025-04 | 2026-10 | 19 | 0 | no |
| browsers | AE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | AR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | AT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | AU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | AU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | BD | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BD | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BD | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BD | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | BE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | BG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | BR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | BR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | CZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | CZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | DE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | DK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | DK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | EE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | EG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | EG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | ES | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ES | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ES | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ES | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | FI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | FR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | FR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | GB | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GB | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GB | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GB | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | GR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | GR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | HK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | HR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | HU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | HU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | ID | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ID | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ID | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ID | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | IE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | IL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | IN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | IT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | IT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | JP | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | JP | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | JP | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | JP | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | KE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | KR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | KR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | LT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | LU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | LV | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LV | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LV | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | LV | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | MA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | MT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | MX | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MX | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MX | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MX | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | MY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | MY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | NG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | NL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | NO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | NZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | NZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | PH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | PK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | PL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | PT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | PT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | RO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | RU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | RU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | SA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | SE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | SG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | SI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | SK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | SK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | TH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | TR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | TW | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TW | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TW | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | TW | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | UA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | UA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | UA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | UA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | US | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | US | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | US | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | US | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | VN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | VN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | VN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | VN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | ZA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ZA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ZA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ZA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | af | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | af | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | af | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | af | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | as | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | as | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | as | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | as | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | eu | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | eu27 | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu27 | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu27 | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | eu27 | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | na | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | na | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | na | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | na | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | oc | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | oc | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | oc | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | oc | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | sa | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | sa | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | sa | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | sa | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| browsers | ww | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ww | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ww | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| browsers | ww | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | AE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | AR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | AT | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AT | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | AU | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AU | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | AU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | BD | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BD | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BD | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | BE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | BG | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BG | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | BR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | BR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CA | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CA | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CH | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CH | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CL | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CL | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CN | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CN | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CO | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CO | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CY | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CY | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | CZ | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CZ | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | CZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | DE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | DE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | DE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | DK | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | DK | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | DK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | EE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | EE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | EE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | EG | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | EG | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | EG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | ES | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ES | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ES | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | FI | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | FI | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | FI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | FR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | FR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | FR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | GB | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | GB | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | GB | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | GR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | GR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | GR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | HK | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HK | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | HR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | HU | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HU | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | HU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | ID | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ID | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ID | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | IE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | IL | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IL | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | IN | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IN | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | IT | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IT | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | IT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | JP | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | JP | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | JP | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | KE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | KE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | KE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | KR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | KR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | KR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | LT | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LT | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | LU | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LU | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | LV | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LV | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | LV | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | MA | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MA | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | MT | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MT | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | MX | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MX | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MX | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | MY | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MY | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | MY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | NG | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NG | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | NL | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NL | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | NO | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NO | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | NZ | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NZ | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | NZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | PH | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PH | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | PK | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PK | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | PL | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PL | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | PT | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PT | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | PT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | RO | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | RO | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | RO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | RU | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | RU | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | RU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | SA | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SA | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | SE | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SE | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | SG | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SG | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | SI | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SI | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | SK | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SK | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | SK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | TH | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TH | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | TR | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TR | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | TW | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TW | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | TW | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | UA | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | UA | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | UA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | US | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | US | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | US | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | VN | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | VN | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | VN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | ZA | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ZA | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ZA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | af | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | af | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | af | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | as | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | as | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | as | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | eu | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | eu | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | eu | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | eu27 | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | eu27 | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | eu27 | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | na | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | na | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | na | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | oc | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | oc | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | oc | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | sa | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | sa | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | sa | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| device-vendors | ww | all | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ww | mobile | 2010-04 | 2026-10 | 199 | 0 | yes |
| device-vendors | ww | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | AE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | AR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | AT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | AU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | AU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | BD | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BD | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BD | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BD | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | BE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | BG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | BR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | BR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | CZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | CZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | DE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | DK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | DK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | EE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | EG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | EG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | ES | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ES | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ES | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ES | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | FI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | FR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | FR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | GB | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GB | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GB | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GB | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | GR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | GR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | HK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | HR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | HU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | HU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | ID | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ID | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ID | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ID | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | IE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | IL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | IN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | IT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | IT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | JP | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | JP | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | JP | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | JP | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | KE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | KR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | KR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | LT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | LU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | LV | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LV | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LV | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | LV | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | MA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | MT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | MX | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MX | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MX | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MX | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | MY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | MY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | NG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | NL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | NO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | NZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | NZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | PH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | PK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | PL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | PT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | PT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | RO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | RU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | RU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | SA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | SE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | SG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | SI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | SK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | SK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | TH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | TR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | TW | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TW | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TW | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | TW | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | UA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | UA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | UA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | UA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | US | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | US | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | US | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | US | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | VN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | VN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | VN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | VN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | ZA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ZA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ZA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ZA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | af | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | af | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | af | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | af | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | as | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | as | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | as | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | as | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | eu | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | eu27 | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu27 | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu27 | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | eu27 | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | na | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | na | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | na | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | na | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | oc | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | oc | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | oc | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | oc | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | sa | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | sa | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | sa | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | sa | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| operating-systems | ww | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ww | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ww | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| operating-systems | ww | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | AE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | AR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | AT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | AU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | AU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | BD | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BD | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BD | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BD | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | BE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | BG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | BR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | BR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | CZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | CZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | DE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | DK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | DK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | EE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | EG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | EG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | ES | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ES | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ES | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ES | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | FI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | FR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | FR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | GB | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GB | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GB | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GB | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | GR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | GR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | HK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | HR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | HU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | HU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | ID | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ID | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ID | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ID | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | IE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | IL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | IN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | IT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | IT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | JP | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | JP | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | JP | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | JP | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | KE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | KR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | KR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | LT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | LU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | LV | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LV | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LV | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | LV | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | MA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | MT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | MX | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MX | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MX | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MX | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | MY | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MY | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MY | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | MY | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | NG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | NL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | NO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | NZ | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NZ | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NZ | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | NZ | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | PH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | PK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | PL | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PL | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PL | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PL | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | PT | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PT | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PT | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | PT | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | RO | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RO | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RO | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RO | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | RU | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RU | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RU | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | RU | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | SA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | SE | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SE | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SE | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SE | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | SG | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SG | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SG | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SG | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | SI | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SI | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SI | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SI | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | SK | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SK | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SK | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | SK | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | TH | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TH | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TH | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TH | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | TR | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TR | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TR | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TR | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | TW | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TW | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TW | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | TW | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | UA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | UA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | UA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | UA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | US | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | US | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | US | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | US | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | VN | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | VN | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | VN | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | VN | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | ZA | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ZA | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ZA | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ZA | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | af | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | af | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | af | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | af | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | as | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | as | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | as | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | as | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | eu | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | eu27 | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu27 | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu27 | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | eu27 | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | na | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | na | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | na | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | na | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | oc | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | oc | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | oc | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | oc | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | sa | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | sa | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | sa | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | sa | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |
| search | ww | all | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ww | desktop | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ww | mobile | 2009-01 | 2026-10 | 214 | 0 | yes |
| search | ww | tablet | 2012-08 | 2026-10 | 171 | 0 | yes |

### Market shares (quarters with figures)

| Segment | Area | Source | First | Last | Quarters | Longest gap | Correlatable |
|---|---|---|---|---|---|---|---|
| cloud | eu | synergy | 2021Q2 | 2022Q2 | 2 | 3 | no |
| cloud | ww | synergy | 2021Q2 | 2026Q2 | 21 | 0 | yes |
| dram | ww | trendforce | 2009Q1 | 2026Q2 | 17 | 23 | no |
| foundry | ww | manual | 2024Q4 | 2024Q4 | 1 | 0 | no |
| foundry | ww | trendforce | 2021Q2 | 2026Q2 | 9 | 8 | no |
| nand | ww | trendforce | 2009Q3 | 2026Q2 | 12 | 44 | no |
| pcs | IN | idc | 2021Q3 | 2026Q2 | 8 | 8 | no |
| pcs | ww | idc | 2021Q3 | 2026Q3 | 21 | 0 | yes |
| smartphones | CN | idc | 2022Q4 | 2026Q3 | 4 | 6 | no |
| smartphones | ID | idc | 2021Q2 | 2022Q4 | 6 | 1 | no |
| smartphones | IN | idc | 2021Q4 | 2026Q2 | 6 | 8 | no |
| smartphones | TH | idc | 2021Q4 | 2022Q4 | 2 | 3 | no |
| smartphones | VN | idc | 2021Q3 | 2022Q3 | 2 | 3 | no |
| smartphones | ww | idc | 2021Q3 | 2026Q3 | 20 | 1 | yes |
| tablets | IN | idc | 2025Q2 | 2026Q2 | 2 | 3 | no |
| tablets | ww | idc | 2021Q3 | 2025Q3 | 15 | 2 | no |
| x86 | ww | manual | 2026Q2 | 2026Q2 | 1 | 0 | no |

### Stock values (months with a close)

| Listing | First | Last | Months | Longest gap | Correlatable |
|---|---|---|---|---|---|
| EPA:OVH | 2021-10 | 2026-10 | 61 | 0 | yes |
| ETR:SAP | 1998-04 | 2026-10 | 343 | 0 | yes |
| HEL:NOKIA | 1991-02 | 2026-10 | 429 | 0 | yes |
| HKG:0700 | 2004-06 | 2026-10 | 269 | 0 | yes |
| HKG:0981 | 2004-03 | 2026-10 | 272 | 0 | yes |
| HKG:0992 | 2000-01 | 2026-10 | 322 | 0 | yes |
| HKG:1347 | 2014-10 | 2026-10 | 145 | 0 | yes |
| HKG:1810 | 2018-07 | 2026-10 | 100 | 0 | yes |
| HKG:9888 | 2021-03 | 2026-10 | 68 | 0 | yes |
| HKG:9988 | 2019-11 | 2026-10 | 84 | 0 | yes |
| KRX:000660 | 2005-09 | 2026-10 | 254 | 0 | yes |
| KRX:005930 | 2005-09 | 2026-10 | 254 | 0 | yes |
| KRX:035420 | 2005-09 | 2026-10 | 254 | 0 | yes |
| KRX:066570 | 2005-09 | 2026-10 | 254 | 0 | yes |
| NASDAQ:AAPL | 1986-10 | 2026-10 | 481 | 0 | yes |
| NASDAQ:AMD | 1986-10 | 2026-10 | 481 | 0 | yes |
| NASDAQ:AMZN | 1997-05 | 2026-10 | 354 | 0 | yes |
| NASDAQ:ARM | 2023-09 | 2026-10 | 38 | 0 | yes |
| NASDAQ:AVGO | 2009-08 | 2026-10 | 207 | 0 | yes |
| NASDAQ:BIDU | 2005-08 | 2026-10 | 255 | 0 | yes |
| NASDAQ:CRWV | 2025-03 | 2026-10 | 20 | 0 | no |
| NASDAQ:CSCO | 1990-02 | 2026-10 | 441 | 0 | yes |
| NASDAQ:GFS | 2021-10 | 2026-10 | 61 | 0 | yes |
| NASDAQ:GOOGL | 2004-08 | 2026-10 | 267 | 0 | yes |
| NASDAQ:INTC | 1986-10 | 2026-10 | 481 | 0 | yes |
| NASDAQ:MSFT | 1986-10 | 2026-10 | 481 | 0 | yes |
| NASDAQ:MU | 1986-10 | 2026-10 | 481 | 0 | yes |
| NASDAQ:NBIS | 2024-10 | 2026-10 | 25 | 0 | no |
| NASDAQ:NVDA | 1999-01 | 2026-10 | 334 | 0 | yes |
| NASDAQ:OPRA | 2018-07 | 2026-10 | 100 | 0 | yes |
| NASDAQ:SNDK | 2025-02 | 2026-10 | 21 | 0 | no |
| NASDAQ:WDC | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:BABA | 2014-09 | 2026-10 | 146 | 0 | yes |
| NYSE:BB | 1999-02 | 2026-10 | 333 | 0 | yes |
| NYSE:DELL | 2016-08 | 2026-10 | 123 | 0 | yes |
| NYSE:HPE | 2015-10 | 2026-10 | 133 | 0 | yes |
| NYSE:HPQ | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:IBM | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:MSI | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:NOK | 1994-07 | 2026-10 | 388 | 0 | yes |
| NYSE:ORCL | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:SAP | 1995-09 | 2026-10 | 374 | 0 | yes |
| NYSE:SONY | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:T | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:TSM | 1997-10 | 2026-10 | 349 | 0 | yes |
| NYSE:UIS | 1986-10 | 2026-10 | 481 | 0 | yes |
| NYSE:UMC | 2000-09 | 2026-10 | 314 | 0 | yes |
| NYSE:VZ | 1986-10 | 2026-10 | 481 | 0 | yes |
| OTCMKTS:TCEHY | 2008-11 | 2026-10 | 215 | 1 | yes |
| SHA:601360 | 2012-01 | 2026-10 | 174 | 4 | no |
| SHA:688036 | 2019-09 | 2026-10 | 86 | 0 | yes |
| SHA:688981 | 2020-07 | 2026-10 | 76 | 0 | yes |
| TPE:2303 | 2000-01 | 2026-10 | 322 | 0 | yes |
| TPE:2330 | 2000-01 | 2026-10 | 322 | 0 | yes |
| TPE:2344 | 2000-01 | 2026-10 | 322 | 0 | yes |
| TPE:2353 | 2000-01 | 2026-10 | 322 | 0 | yes |
| TPE:2357 | 2000-01 | 2026-10 | 322 | 0 | yes |
| TPE:2408 | 2000-08 | 2026-10 | 315 | 0 | yes |
| TPE:2498 | 2002-03 | 2026-10 | 296 | 0 | yes |
| TYO:285A | 2024-12 | 2026-10 | 23 | 0 | no |
| TYO:6758 | 2000-01 | 2026-10 | 322 | 0 | yes |
<!-- markets:coverage:end -->

## 7. How to run

```bash
uv run migrate-db upgrade                                         # tables market_shares, stock_prices, fx_rates (0009, 0010)
CRAWLER_SOURCE=markets uv run python src/main.py                  # every source: FRED, World Bank, Google Finance, StatCounter, TrendForce, IDC
CRAWLER_SOURCE=markets CRAWLER_TARGET=google-finance,fred uv run python src/main.py
CRAWLER_SOURCE=markets CRAWLER_TARGET=statcounter MARKETS_AREAS=ww,US,GB,DE,FR uv run python src/main.py
CRAWLER_SOURCE=markets MARKETS_SINCE=2026-07 uv run python src/main.py   # the last months only, to keep up to date
uv run render-markets-doc --coverage                              # print section 6
```

- `CRAWLER_TARGET` picks the sources: `statcounter` (the World Bank weights join it), `google-finance`, `fred`, `worldbank`, `trendforce`, `idc`, or every one by default.
- `MARKETS_AREAS` limits the StatCounter areas, `MARKETS_LISTINGS` the listings (`NYSE:IBM,TPE:2330`), and `MARKETS_SINCE` (`YYYY-MM`) the months read.
- A full crawl makes about 1,350 StatCounter requests (71 areas × 19 statistic-device pairs, 2 s apart, about 50 minutes), 48 Google Finance requests and 14 FRED requests. It stores about 4 million shares. After the crawls it estimates the EU-27, turns the stored Synergy reports into cloud shares, and writes the stock measures of the providers.

## 8. In the application

- **Crawling from the window**: the toolbar has a list of the markets sources ("Every markets source", TrendForce, IDC, World Bank, FRED, Google Finance, StatCounter) and a "Crawl markets" button. The **Markets** menu offers the same choices. A crawl runs in the background, as the command line runs it (StatCounter brings the World Bank weights with it), then derives the EU-27 estimate, the manual points, the Synergy shares and the stock measures, and refreshes the three cards. The button is disabled while a crawl runs.
- **Market shares**: pick a segment, an area (type to search, flags shown), the devices and the top N companies. There is one line per company in its chronology colour, then "Others". Hover a date to list every line's value there, and click a legend entry to hide its line.
- **Stock values**: pick listings (by company, grouped by region of headquarters), region indexes or valuation points. Then the currency (listing, USD, EUR, GBP), the scale (indexed, log, linear) and whether the secondary listings show.
- **Share vs stock**: pick a company of the share chart and correlate. The bars are ρ by lag with their 95% interval, solid when q < 5%. The text gives the strongest lag and the Granger p-values, or why nothing was computed.
- The "Notable events" picked in the leaders card are drawn on both time charts as dashed red markers, the policy-shock look of mega-trends. A click on a leader band opens the share card on its segment and the stock card on its company.
