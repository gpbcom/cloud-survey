from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class Specification(StrEnum):
    """Enums representing which controls a compounding model holds constant.

    Attributes:
        BASE (str): The catalogue size, the growth of the cloud market and the age of the category (S1).
        SHARE (str): The same plus the provider's share of the cloud market, on the years it is known (S2).
    """

    BASE = "base"
    SHARE = "share"


@unique
class FoundationSource(StrEnum):
    """Enums representing where the foundations of a category come from.

    Attributes:
        CURATED (str): The links read from architecture documents (`conf/analysis/compounding.yaml`).
        DATA_DRIVEN (str): The categories the other providers entered before it.
    """

    CURATED = "curated"
    DATA_DRIVEN = "data-driven"


@unique
class CurveKind(StrEnum):
    """Enums representing a growth curve fitted to a provider's catalogue size.

    Attributes:
        EXPONENTIAL (str): A launch rate linear in the catalogue size, without ceiling (equation 6.6).
        LOGISTIC (str): Self-reinforcing growth towards a ceiling.
        BASS (str): Steady and self-reinforcing launches towards a ceiling (equation 6.7).
        MARKET (str): The catalogue proportional to a power of the cloud-market size (the rival explanation).
    """

    EXPONENTIAL = "exponential"
    LOGISTIC = "logistic"
    BASS = "bass"
    MARKET = "market"


@unique
class FitKind(StrEnum):
    """Enums representing a model of the entry of a provider into a category.

    Attributes:
        ENTRY (str): The entry explained by the density of the related categories held (equation 6.5).
        HAZARD (str): The entry explained by the share of the category's foundations held (equation 6.13).
    """

    ENTRY = "entry"
    HAZARD = "hazard"


@unique
class Verdict(StrEnum):
    """Enums representing what the models say about a provider.

    Attributes:
        SUPPORTS (str): The foundations held raise the entry and beat the placebo.
        MIXED (str): Some evidence, not all of it significant.
        AGAINST (str): The foundations held do not raise the entry.
        INSUFFICIENT (str): Too few entries to tell.
    """

    SUPPORTS = "supports"
    MIXED = "mixed"
    AGAINST = "against"
    INSUFFICIENT = "insufficient"


@unique
class CompoundingWarningKind(StrEnum):
    """Enums representing a caveat of a compounding analysis.

    Attributes:
        FEW_EVENTS (str): A provider entered too few categories for its own fit.
        NO_SHARE (str): A provider has no market share for the years fitted.
        EXCLUDED (str): A provider is outside the public-cloud scope and fitted apart.
        NOT_CONVERGED (str): A fit did not converge (separation or too few rows).
        MARKET_FALLBACK (str): Some market sizes come from the curated fallback, not from the crawl.
        NO_DATA (str): A provider has no dated product in the database.
    """

    FEW_EVENTS = "few-events"
    NO_SHARE = "no-share"
    EXCLUDED = "excluded"
    NOT_CONVERGED = "not-converged"
    MARKET_FALLBACK = "market-fallback"
    NO_DATA = "no-data"


@unique
class ValueOrigin(StrEnum):
    """Enums representing where a yearly input value comes from.

    Attributes:
        CRAWLED (str): Read by a crawl (Synergy articles).
        MANUAL (str): Typed in a curated file with its source.
        NONE (str): Unknown for that year.
        INTERPOLATED (str): Summed from crawled quarters, the missing ones interpolated between their neighbours.
    """

    CRAWLED = "crawled"
    MANUAL = "manual"
    NONE = "none"
    INTERPOLATED = "interpolated"


@unique
class CompoundingControl(StrEnum):
    """Enums representing a control of the Service compounding section (each explained in its help file).

    Attributes:
        PROVIDERS (str): The providers analysed.
        SPECIFICATION (str): The controls held constant.
        LAG (str): How many years the foundations are held before the entry.
        FOUNDATIONS (str): Where the foundations come from.
        RUN (str): The run button.
        EXPORT (str): The export button.
        CRAWL_HISTORY (str): The button crawling the Synergy history.
        CRAWL_ALL (str): The button crawling every source of the analysis.
        DERIVATIVE (str): The rate-of-change switch of the line charts.
    """

    PROVIDERS = "providers"
    SPECIFICATION = "specification"
    LAG = "lag"
    FOUNDATIONS = "foundations"
    RUN = "run"
    EXPORT = "export"
    CRAWL_HISTORY = "crawl-history"
    CRAWL_ALL = "crawl-all"
    DERIVATIVE = "derivative"


@unique
class CompoundingColumn(StrEnum):
    """Enums representing a column of the Service compounding tables (each explained in its help file).

    Attributes:
        PROVIDER (str): The provider, or the pooled fit.
        PRODUCTS (str): The dated products kept.
        HELD (str): The products held at the start of the window (not counted as launches).
        WINDOW (str): The years observed.
        EVENTS (str): The categories entered in the window.
        SHARE_YEARS (str): The years with a market share.
        HEAPS (str): The slope of the distinct categories on the catalogue size (log-log).
        GROWTH (str): The launch rate per product already held (b of equation 6.6).
        BEST_CURVE (str): The growth curve with the lowest AIC.
        DENSITY (str): The coefficient of the density of related categories (equation 6.5).
        FOUNDATIONS (str): The coefficient of the share of foundations held (beta 1 of equation 6.13).
        EXPERIENCE (str): The coefficient of the years of experience in the foundations (beta 2).
        SIZE (str): The coefficient of the catalogue size.
        SHARE (str): The coefficient of the market share.
        MARKET (str): The coefficient of the growth of the cloud market.
        PLACEBO (str): The share of placebo foundation sets doing at least as well.
        TRANSFER (str): The gain of predictive accuracy when the AWS model predicts this provider.
        VERDICT (str): What the models say.
    """

    PROVIDER = "provider"
    PRODUCTS = "products"
    HELD = "held"
    WINDOW = "window"
    EVENTS = "events"
    SHARE_YEARS = "share-years"
    HEAPS = "heaps"
    GROWTH = "growth"
    BEST_CURVE = "best-curve"
    DENSITY = "density"
    FOUNDATIONS = "foundations"
    EXPERIENCE = "experience"
    SIZE = "size"
    SHARE = "share"
    MARKET = "market"
    PLACEBO = "placebo"
    TRANSFER = "transfer"
    VERDICT = "verdict"


class CompoundingCard(StrEnum):
    """Enums representing a card of the Service compounding section (each explained in its help file).

    Attributes:
        CONTROLS (str): The pickers, the coverage and the crawl buttons.
        LAUNCHES (str): The yearly launches and catalogue size of each provider.
        MARKET (str): The yearly size of the cloud market.
        SHARES (str): The yearly cloud-market share of each provider.
        HEAPS (str): Heaps' law: distinct categories against catalogue size.
        GROWTH (str): The growth curves of the catalogues.
        ENTRY (str): The density model of the entries.
        HAZARD (str): The foundation hazard of the entries.
        PLACEBO (str): The placebo test of the foundation coefficient.
        LAGS (str): The foundation coefficient at every lag.
        TRANSFER (str): The predictions of the AWS model for the other providers.
        SUMMARY (str): What every model says about each provider.
        FOUNDATIONS (str): The foundation sets, the providers and the domains kept.
    """

    CONTROLS = "controls"
    LAUNCHES = "launches"
    MARKET = "market"
    SHARES = "shares"
    HEAPS = "heaps"
    GROWTH = "growth"
    ENTRY = "entry"
    HAZARD = "hazard"
    PLACEBO = "placebo"
    LAGS = "lags"
    TRANSFER = "transfer"
    SUMMARY = "summary"
    FOUNDATIONS = "foundations"
