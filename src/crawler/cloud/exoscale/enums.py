from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ExoscaleMenuMarkup(StrEnum):
    """Enums representing the HTML markup of the Exoscale products menu compared by the crawler.

    Attributes:
        GROUP (str): The CSS class of a group of menu entries.
    """

    GROUP = "mega__group"


@unique
class ExoscaleRequestMeta(StrEnum):
    """Enums representing the request meta keys of the Exoscale marketplace crawler.

    Attributes:
        LISTING (str): Marks a listing page request, holding the requested URL.
        SITEMAP (str): Marks the sitemap request.
    """

    LISTING = "listing"
    SITEMAP = "sitemap"


@unique
class ExoscaleMarketplaceSection(StrEnum):
    """Enums representing the identifiers of the Exoscale marketplace sections.

    Attributes:
        TEMPLATES (str): The compute instance templates.
        MANAGED_SERVICES (str): The managed services.
        POWERED_BY_EXOSCALE (str): The software powered by Exoscale.
    """

    TEMPLATES = "templates"
    MANAGED_SERVICES = "managed-services"
    POWERED_BY_EXOSCALE = "powered-by-exoscale"


@unique
class ExoscaleChangelogMarkup(StrEnum):
    """Enums representing the CSS selectors of the Exoscale changelog read for the launches.

    Attributes:
        CARD (str): An entry of the changelog.
        DATE (str): The date of an entry, e.g. `Jan 28, 2022`.
        TITLE (str): The title link of an entry.
        TAG (str): The tag links of an entry, e.g. `/tags/dbaas/`.
    """

    CARD = ".changelog-card"
    DATE = "time::text"
    TITLE = "h2.card-title a"
    TAG = "a.tag"


@unique
class ExoscaleChangelogTag(StrEnum):
    """Enums representing the Exoscale changelog tags compared by the crawler.

    Attributes:
        NEW (str): Marks the entries announcing something new.
        MARKETPLACE (str): Marks the marketplace entries, about partner products.
        PARTNERS (str): Marks the partner entries, about partner products.
        ACADEMY (str): Marks the academy entries, about courses and exams.
    """

    NEW = "new"
    MARKETPLACE = "marketplace"
    PARTNERS = "partners"
    ACADEMY = "academy"


@unique
class ExoscaleLaunchKeyword(StrEnum):
    """Enums representing the words of an Exoscale changelog title announcing a launch.

    Attributes:
        NOW_AVAILABLE (str): `... now available`.
        AVAILABLE (str): `... available`.
        LAUNCH (str): `... launch`.
        LAUNCHED (str): `... launched`.
        GENERAL_AVAILABILITY (str): `... General Availability`.
        GA (str): `... GA`.
        PREVIEW (str): `... (Preview)`.
        BETA (str): `... beta`.
    """

    NOW_AVAILABLE = "now available"
    AVAILABLE = "available"
    LAUNCH = "launch"
    LAUNCHED = "launched"
    GENERAL_AVAILABILITY = "general availability"
    GA = "ga"
    PREVIEW = "preview"
    BETA = "beta"


@unique
class ExoscalePriceColumn(StrEnum):
    """Enums representing the columns of the tables of the Exoscale pricing page read for the prices.

    Attributes:
        RAM (str): The memory of an instance.
        MEMORY (str): The memory of a managed database node.
        CPU_CORES (str): The cores of an instance.
        CPU (str): The cores of a managed database node.
        MIN_LOCAL_STORAGE (str): The least local storage of an instance.
        VOLUME_SIZE (str): The storage of a managed database plan.
        ALLOCATED_DISK (str): The storage of a managed ClickHouse plan.
        PRODUCT_DETAILS (str): What a service price is per (`per GiB.hour`, `One-Off Setup Cost`).
        INFORMATION (str): The documentation link of a service (not an attribute).
        AVAILABILITY (str): The availability of a model (not a price).
    """

    RAM = "RAM"
    MEMORY = "Memory"
    CPU_CORES = "CPU Cores"
    CPU = "CPU"
    MIN_LOCAL_STORAGE = "Min Local Storage"
    VOLUME_SIZE = "Volume size"
    ALLOCATED_DISK = "Allocated disk"
    PRODUCT_DETAILS = "Product Details"
    INFORMATION = "Information"
    AVAILABILITY = "Availability"


@unique
class ExoscalePriceLiteral(StrEnum):
    """Enums representing the words the Exoscale pricing page writes instead of a price (case-folded).

    Attributes:
        FREE (str): The service is free.
        INCLUDED (str): The service is included in another one.
        NOT_APPLICABLE (str): The dimension does not apply (no price).
        NONE (str): No price (a dash).
    """

    FREE = "free"
    INCLUDED = "included"
    NOT_APPLICABLE = "not applicable"
    NONE = "-"
