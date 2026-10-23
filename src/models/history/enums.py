from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class EventKind(StrEnum):
    """Enums representing the kinds of notable events of the computing chronology.

    Attributes:
        REGULATION (str): An antitrust case, a fine, a regulatory decision or designation.
        ACQUISITION (str): An acquisition or a merger.
        BANKRUPTCY (str): A bankruptcy or a liquidation.
        LISTING (str): An initial public offering.
        FUNDING (str): A private funding round.
        PRODUCT (str): A product launch that changed a market.
        MARKET_ACCESS (str): Export controls, sanctions or a market exit (access to a national market).
    """

    REGULATION = "regulation"
    ACQUISITION = "acquisition"
    BANKRUPTCY = "bankruptcy"
    LISTING = "listing"
    FUNDING = "funding"
    PRODUCT = "product"
    MARKET_ACCESS = "market-access"


@unique
class EventOutcome(StrEnum):
    """Enums representing what an intervention changed (the verdicts of the dossier).

    Attributes:
        STRUCTURAL (str): It reshaped the market structure.
        TIMING_ONLY (str): It changed the timing and the price of a rise or a fall, not its direction.
        NO_DIRECTION_CHANGE (str): The targeted firm kept its position.
        REMOVED_DOWNSIDE (str): It removed a threat hanging over the firm.
        PENDING (str): Too early to tell.
        NEUTRAL (str): No visible effect beyond compliance costs.
    """

    STRUCTURAL = "structural"
    TIMING_ONLY = "timing-only"
    NO_DIRECTION_CHANGE = "no-direction-change"
    REMOVED_DOWNSIDE = "removed-downside"
    PENDING = "pending"
    NEUTRAL = "neutral"


@unique
class AdoptionCriterion(StrEnum):
    """Enums representing the adoption criteria the dossier rates as decisive for a rise or a fall.

    Attributes:
        RELATIVE_ADVANTAGE (str): Clearly better than what it replaces.
        PORTABILITY (str): Runs on many platforms.
        PROFITABILITY (str): Profitable enough to fund its growth (or its fall shows as profit collapse).
        COMPLEXITY (str): Easy or hard to adopt.
        OBSERVABILITY (str): Its benefits are visible to others.
        SECURITY (str): Trusted with sensitive data.
        RELIABILITY (str): Dependable in operation.
        COMPATIBILITY (str): Works with what customers already have (standards, lock-in).
    """

    RELATIVE_ADVANTAGE = "relative-advantage"
    PORTABILITY = "portability"
    PROFITABILITY = "profitability"
    COMPLEXITY = "complexity"
    OBSERVABILITY = "observability"
    SECURITY = "security"
    RELIABILITY = "reliability"
    COMPATIBILITY = "compatibility"


@unique
class DatePrecision(StrEnum):
    """Enums representing how precisely a date of the chronology is known.

    Attributes:
        YEAR (str): `YYYY`.
        MONTH (str): `YYYY-MM`.
        DAY (str): `YYYY-MM-DD`.
    """

    YEAR = "year"
    MONTH = "month"
    DAY = "day"
