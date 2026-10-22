from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class TCloudRequestMeta(StrEnum):
    """Enums representing the request meta keys of the T Cloud Public marketplace crawler.

    Attributes:
        CATEGORIES (str): Marks the categories API request.
    """

    CATEGORIES = "categories"


@unique
class TCloudApiField(StrEnum):
    """Enums representing the keys of the T Cloud Public marketplace API objects (categories and products).

    Attributes:
        ID (str): The identifier of a category or a product.
        NAME (str): The name of a category, a product or a seller.
        CATEGORIES (str): The category identifiers of a product.
        DESCRIPTION_SHORT (str): The short description of a product.
        DESCRIPTION (str): The long (HTML) description of a product.
        SELLER (str): The seller object of a product.
        TYPE (str): The type of a product, giving its delivery method.
        CREATED_AT (str): The listing date of a product.
    """

    ID = "id"
    NAME = "name"
    CATEGORIES = "categories"
    DESCRIPTION_SHORT = "description_short"
    DESCRIPTION = "description"
    SELLER = "seller"
    TYPE = "type"
    CREATED_AT = "created_at"


@unique
class TCloudServiceCategory(StrEnum):
    """Enums representing the T Cloud Public marketplace categories of the professional services offers.

    Attributes:
        ADVISORY_ASSESSMENT (str): The advisory and assessment offers.
        BUILD_MIGRATE (str): The build and migration offers.
        OPTIMIZE_SECURE (str): The optimization and security offers.
    """

    ADVISORY_ASSESSMENT = "Advisory & Assessment"
    BUILD_MIGRATE = "Build & Migrate"
    OPTIMIZE_SECURE = "Optimize & Secure"


@unique
class TCloudServiceSeller(StrEnum):
    """Enums representing the T Cloud Public marketplace sellers of professional services only.

    Attributes:
        T_SYSTEMS_PROFESSIONAL_SERVICES (str): The T-Systems cloud professional services.
    """

    T_SYSTEMS_PROFESSIONAL_SERVICES = "T-Systems | Cloud Professional Services"


@unique
class TCloudProductType(StrEnum):
    """Enums representing the T Cloud Public marketplace product types.

    Attributes:
        LEAD_GENERATION (str): A software sold by the vendor itself, delivered as a service.
        CONTAINER (str): A container image.
        LLM_TPM (str): A large language model billed by tokens per minute.
    """

    LEAD_GENERATION = "lead-generation"
    CONTAINER = "container"
    LLM_TPM = "llm-tpm"
