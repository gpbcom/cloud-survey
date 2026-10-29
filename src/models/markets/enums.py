from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class MarketFeed(StrEnum):
    """Enums representing the sources the markets crawl reads (`CRAWLER_SOURCE=markets`, `CRAWLER_TARGET`).

    Attributes:
        STATCOUNTER (str): StatCounter Global Stats, the monthly usage shares (search, browsers, OS, vendors, AI).
        GOOGLE_FINANCE (str): Google Finance, the weekly closing prices of the listings.
        FRED (str): FRED (Federal Reserve Bank of St. Louis), the daily exchange rates against the US dollar.
        WORLD_BANK (str): The World Bank indicators weighting the member states of the EU-27 estimate.
        TRENDFORCE (str): TrendForce press releases, the quarterly shares of the foundries and memory makers.
        IDC (str): IDC press releases, the quarterly shares of the PC, smartphone and tablet makers.
    """

    STATCOUNTER = "statcounter"
    GOOGLE_FINANCE = "google-finance"
    FRED = "fred"
    WORLD_BANK = "worldbank"
    TRENDFORCE = "trendforce"
    IDC = "idc"


@unique
class ShareSource(StrEnum):
    """Enums representing where a stored market share comes from.

    Attributes:
        STATCOUNTER (str): StatCounter Global Stats (share of page views).
        SYNERGY (str): Synergy Research Group (share of cloud revenue), read from the stored market reports.
        MANUAL (str): A point of the source dossier, typed in the catalogue.
        TRENDFORCE (str): TrendForce press releases (share of revenue).
        IDC (str): IDC press releases (share of unit shipments).
    """

    STATCOUNTER = "statcounter"
    SYNERGY = "synergy"
    MANUAL = "manual"
    TRENDFORCE = "trendforce"
    IDC = "idc"


@unique
class ShareMetric(StrEnum):
    """Enums representing what a market share is a share of.

    Attributes:
        USAGE (str): Usage: page views, visits or requests (StatCounter).
        UNITS (str): Units shipped or sold.
        REVENUE (str): Revenue.
    """

    USAGE = "usage"
    UNITS = "units"
    REVENUE = "revenue"


@unique
class Device(StrEnum):
    """Enums representing the devices a usage share is measured on.

    Attributes:
        ALL (str): Every device (desktop, mobile, tablet and console).
        DESKTOP (str): Desktop and laptop computers.
        MOBILE (str): Phones.
        TABLET (str): Tablets.
    """

    ALL = "all"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"


@unique
class Granularity(StrEnum):
    """Enums representing the period a market share covers.

    Attributes:
        MONTH (str): A calendar month.
        QUARTER (str): A calendar quarter.
        YEAR (str): A calendar year.
    """

    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@unique
class StatCounterStat(StrEnum):
    """Enums representing the StatCounter statistics read (the `statType_hidden` of its CSV export).

    Attributes:
        SEARCH_ENGINE (str): Search engines.
        BROWSER (str): Web browsers.
        OS_COMBINED (str): Operating systems, desktop and mobile together.
        VENDOR (str): Device vendors.
        AI_CHATBOT (str): AI chatbots (from April 2025).
    """

    SEARCH_ENGINE = "search_engine"
    BROWSER = "browser"
    OS_COMBINED = "os_combined"
    VENDOR = "vendor"
    AI_CHATBOT = "ai_chatbot"


@unique
class AreaKind(StrEnum):
    """Enums representing the kinds of geographic areas a market share is measured in.

    Attributes:
        WORLD (str): The whole world.
        CONTINENT (str): A continent, as StatCounter draws it.
        COUNTRY (str): A country (ISO 3166-1 alpha-2).
        UNION (str): A union of countries estimated from its members (the EU-27).
    """

    WORLD = "world"
    CONTINENT = "continent"
    COUNTRY = "country"
    UNION = "union"


@unique
class ValuationKind(StrEnum):
    """Enums representing the kinds of sourced valuation points of the companies without a price history.

    Attributes:
        IPO (str): The valuation at an initial public offering.
        DEAL (str): The value of an acquisition.
        MARKET_CAP (str): A market capitalisation on a stated date.
        PRIVATE_ROUND (str): The post-money valuation of a private funding round.
    """

    IPO = "ipo"
    DEAL = "deal"
    MARKET_CAP = "market-cap"
    PRIVATE_ROUND = "private-round"


@unique
class FxQuote(StrEnum):
    """Enums representing how a FRED exchange-rate series is quoted.

    Attributes:
        USD_PER_UNIT (str): US dollars for one unit of the currency (e.g. `DEXUSEU`).
        UNITS_PER_USD (str): Units of the currency for one US dollar (e.g. `DEXJPUS`).
    """

    USD_PER_UNIT = "usd-per-unit"
    UNITS_PER_USD = "units-per-usd"


@unique
class WeightIndicator(StrEnum):
    """Enums representing the World Bank indicators weighting the members of a union.

    Attributes:
        INTERNET_USERS (str): Individuals using the internet, in % of the population.
        POPULATION (str): The total population.
    """

    INTERNET_USERS = "IT.NET.USER.ZS"
    POPULATION = "SP.POP.TOTL"


@unique
class PriceScale(StrEnum):
    """Enums representing how the stock chart scales the prices.

    Attributes:
        LINEAR (str): The prices, on a linear axis.
        LOG (str): The prices, on a logarithmic axis.
        INDEXED (str): Each series rebased to 100 at the start of the window, on a logarithmic axis.
    """

    LINEAR = "linear"
    LOG = "log"
    INDEXED = "indexed"


@unique
class StockView(StrEnum):
    """Enums representing what the stock chart shows.

    Attributes:
        LISTINGS (str): A line per listing of the companies picked.
        REGIONS (str): An equal-weight index per region of headquarters.
        VALUATIONS (str): The sourced valuation points (IPOs, deals, private rounds, market caps), in USD bn.
    """

    LISTINGS = "listings"
    REGIONS = "regions"
    VALUATIONS = "valuations"


@unique
class CorrelationCounterpart(StrEnum):
    """Enums representing what a company's share changes are correlated with in the "Share vs …" card.

    Attributes:
        STOCK (str): The returns of the company's primary listing, in US dollars (Google Finance, FRED).
        SHARE (str): The changes of the company's share in another segment, area or source.
        CURRENCY (str): The changes of the home currency of the company against the US dollar (FRED).
        CONTEXT (str): The changes of a chip supplier concentration (TrendForce HHI), a market context.
    """

    STOCK = "stock"
    SHARE = "share"
    CURRENCY = "currency"
    CONTEXT = "context"


@unique
class MarketControl(StrEnum):
    """Enums representing the controls of the markets cards, each explained by a tooltip (`conf/help.yaml`).

    Attributes:
        SEGMENT (str): The segment of the share chart.
        AREA (str): The area of the share chart.
        DEVICE (str): The devices of the share chart.
        TOP (str): How many companies the share chart draws on their own line.
        VIEW (str): What the stock chart shows.
        COMPANIES (str): The companies of the stock chart.
        CURRENCY (str): The currency of the stock chart.
        SCALE (str): The scale of the stock chart.
        SECONDARY (str): Whether the stock chart draws the secondary listings.
        COMPANY (str): The company of the correlation card.
        AGAINST (str): What the company's share changes are correlated with.
        CORRELATE (str): The button running the correlation.
        DERIVATIVE (str): Whether a time chart draws the rate of change of each line instead of its values.
    """

    SEGMENT = "segment"
    AREA = "area"
    DEVICE = "device"
    TOP = "top"
    VIEW = "view"
    COMPANIES = "companies"
    CURRENCY = "currency"
    SCALE = "scale"
    SECONDARY = "secondary"
    COMPANY = "company"
    AGAINST = "against"
    CORRELATE = "correlate"
    DERIVATIVE = "derivative"
