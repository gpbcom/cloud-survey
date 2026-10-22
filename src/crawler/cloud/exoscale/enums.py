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
