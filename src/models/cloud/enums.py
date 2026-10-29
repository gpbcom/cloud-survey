from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique
from typing import Dict, Final, Optional


@unique
class GeoBloc(StrEnum):
    """Enums representing the geopolitical blocs the cloud providers and market players belong to.

    Attributes:
        UNITED_STATES (str): The United States.
        EUROPEAN_UNION (str): The European Union member states.
        CHINA (str): China.
        RUSSIA (str): Russia.
        OTHER (str): Every other country, e.g. the United Kingdom and Switzerland, and the unattributed aggregates.
    """

    UNITED_STATES = "us"
    EUROPEAN_UNION = "eu"
    CHINA = "cn"
    RUSSIA = "ru"
    OTHER = "other"


@unique
class Country(StrEnum):
    """Enums representing the countries of the cloud providers, as ISO 3166-1 alpha-2 codes.

    Attributes:
        UNITED_STATES (str): United States.
        FRANCE (str): France.
        BELGIUM (str): Belgium.
        GERMANY (str): Germany.
        ITALY (str): Italy.
        LUXEMBOURG (str): Luxembourg.
        SPAIN (str): Spain.
        SWITZERLAND (str): Switzerland.
        UNITED_KINGDOM (str): United Kingdom.
        CHINA (str): China.
        RUSSIA (str): Russia.
    """

    UNITED_STATES = "us"
    FRANCE = "fr"
    BELGIUM = "be"
    GERMANY = "de"
    ITALY = "it"
    LUXEMBOURG = "lu"
    SPAIN = "es"
    SWITZERLAND = "ch"
    UNITED_KINGDOM = "gb"
    CHINA = "cn"
    RUSSIA = "ru"

    @property
    def bloc(self) -> GeoBloc:
        """Get the geopolitical bloc of the country.

        Returns:
            GeoBloc: The bloc, `OTHER` for a country outside the United States, the European Union, China and
                Russia.
        """
        return COUNTRY_BLOCS[self]


@unique
class CloudProvider(StrEnum):
    """Enums representing the Cloud Provider supported, grouped by country.

    Attributes:
        AWS (str): Amazon Web Services.
        AZURE (str): Microsoft Azure.
        GCP (str): Google Cloud Platform.
        IBM (str): IBM Cloud.
        ORACLE (str): Oracle Cloud.
        OVH (str): OVHcloud.
        SCALEWAY (str): Scaleway (Iliad group).
        COMBELL (str): Combell (Belgium).
        PROXIMUS (str): Proximus NXT (Belgium).
        STACKIT (str): STACKIT (Schwarz group, Germany).
        TCLOUD (str): T Cloud Public, formerly Open Telekom Cloud (Germany).
        ARUBA (str): Aruba Cloud (Italy).
        SEEWEB (str): Seeweb (Italy).
        GCORE (str): Gcore (Luxembourg).
        DEEP (str): DEEP, by POST Luxembourg.
        ARSYS (str): Arsys (Spain).
        GIGAS (str): Gigas (Spain).
        EXOSCALE (str): Exoscale (Switzerland).
        INFOMANIAK (str): Infomaniak (Switzerland).
        CIVO (str): Civo (United Kingdom).
        KRYSTAL (str): Krystal, including Katapult (United Kingdom).
        ALIBABA (str): Alibaba Cloud.
        HUAWEI (str): Huawei Cloud.
        TENCENT (str): Tencent Cloud.
        BAIDU (str): Baidu AI Cloud.
        VOLCENGINE (str): Volcano Engine (ByteDance).
        CTYUN (str): China Telecom Cloud (Tianyi Cloud).
        ECLOUD (str): China Mobile Cloud (ecloud).
        YANDEX_CLOUD (str): Yandex Cloud (Russia).
        VK_CLOUD (str): VK Cloud, formerly Mail.ru Cloud Solutions (Russia).
        CLOUD_RU (str): Cloud.ru, formerly SberCloud (Russia).
        SELECTEL (str): Selectel (Russia).
    """

    AWS = "amazon-web-services"
    AZURE = "microsoft-azure"
    GCP = "google-cloud-platform"
    IBM = "ibm-cloud"
    ORACLE = "oracle-cloud"
    OVH = "ovh-cloud"
    SCALEWAY = "scaleway"
    COMBELL = "combell"
    PROXIMUS = "proximus-nxt"
    STACKIT = "stackit"
    TCLOUD = "t-cloud-public"
    ARUBA = "aruba-cloud"
    SEEWEB = "seeweb"
    GCORE = "gcore"
    DEEP = "deep-post-luxembourg"
    ARSYS = "arsys"
    GIGAS = "gigas"
    EXOSCALE = "exoscale"
    INFOMANIAK = "infomaniak"
    CIVO = "civo"
    KRYSTAL = "krystal"
    ALIBABA = "alibaba-cloud"
    HUAWEI = "huawei-cloud"
    TENCENT = "tencent-cloud"
    BAIDU = "baidu-ai-cloud"
    VOLCENGINE = "volcano-engine"
    CTYUN = "china-telecom-cloud"
    ECLOUD = "china-mobile-cloud"
    YANDEX_CLOUD = "yandex-cloud"
    VK_CLOUD = "vk-cloud"
    CLOUD_RU = "cloud-ru"
    SELECTEL = "selectel"

    @property
    def country(self) -> Country:
        """Get the country of the cloud provider, where it is headquartered.

        Returns:
            Country: The country.
        """
        return PROVIDER_COUNTRIES[self]

    @property
    def bloc(self) -> GeoBloc:
        """Get the geopolitical bloc of the cloud provider: the bloc of its country.

        Returns:
            GeoBloc: The bloc.
        """
        return self.country.bloc


@unique
class PricingPolicy(StrEnum):
    """Enums representing the pricing policy of a given service.

    Attributes:
        BY_ARTIFACT (str): Billing by artifact deployed (pod, numbers of documents, etc...).
        BY_RESOURCE (str): Billing by resource consumptions (RAM, CPU).
    """

    BY_ARTIFACT = "artifacts-billing"
    BY_RESOURCE = "resources-billing"


@unique
class SoftwareCategory(StrEnum):
    """Enums representing who a marketplace software is meant for.

    Attributes:
        DEVELOPER_TOOL (str): Software used by developers and IT teams to build and run applications.
        END_USER_SOFTWARE (str): Software used by the business users.
    """

    DEVELOPER_TOOL = "developer-tool"
    END_USER_SOFTWARE = "end-user-software"


@unique
class SoftwareAudience(StrEnum):
    """Enums representing who a marketplace software is meant for, a software of both categories counted apart.

    Attributes:
        DEVELOPER_TOOL (str): Software for the developers and IT teams only.
        END_USER_SOFTWARE (str): Software for the business users only.
        BOTH (str): Software for both: developer tool and end-user software.
    """

    DEVELOPER_TOOL = "developer-tool"
    END_USER_SOFTWARE = "end-user-software"
    BOTH = "both"


@unique
class DeliveryMethod(StrEnum):
    """Enums representing how a marketplace software is delivered.

    Attributes:
        SAAS (str): Software as a service, run by its vendor.
        VIRTUAL_MACHINE (str): Virtual machine image.
        CONTAINER (str): Container image.
        KUBERNETES (str): Kubernetes application (Helm chart, operator, manifests).
        API (str): API or MCP service.
        AI_MODEL (str): Artificial intelligence model or algorithm.
        ONE_CLICK_APP (str): Application installed in one click on a hosting or server offer.
        DOWNLOAD (str): Software license or package to install.
        OTHER (str): Any other delivery method.
    """

    SAAS = "saas"
    VIRTUAL_MACHINE = "virtual-machine"
    CONTAINER = "container"
    KUBERNETES = "kubernetes"
    API = "api"
    AI_MODEL = "ai-model"
    ONE_CLICK_APP = "one-click-app"
    DOWNLOAD = "download"
    OTHER = "other"


@unique
class DateSource(StrEnum):
    """Enums representing where the date of a product or software comes from.

    Attributes:
        WEBSITE (str): Published by the cloud provider's website.
        CRAWL (str): Observed by comparing a crawl with the previous one.
    """

    WEBSITE = "website"
    CRAWL = "crawl"


@unique
class DateCaveat(StrEnum):
    """Enums representing why a date published by a website may not be the date of the product or software itself.

    Attributes:
        PAGE_MODIFIED (str): When the web page was last modified, which may be a change of the page only.
        PAGE_PUBLISHED (str): When the web page was published, which may differ from the launch.
        CATALOGUE_ENTRY (str): When the entry of the provider's catalogue or directory was published or edited, which
            may differ from the launch or from a change of the product.
        WEBSITE_RECORD (str): When the page record was created in the provider's website, often by a website
            migration, long after the launch.
        ASSUMED_TIMEZONE (str): Read from an identifier without timezone, China's timezone is assumed (a few hours
            of uncertainty).
        YEAR_ONLY (str): Only the year is published, the date is the 1st of January of that year.
        OLDEST_VERSION (str): The release of the oldest version still listed, older versions may have been removed.
        FIRST_ANNOUNCEMENT (str): The earliest entry naming the product in the provider's updates feed or release
            notes (preview or general availability, whichever is earlier): the launch is on or before it.
        FEED_START (str): That earliest entry falls in the first months of the feed, the product may be older.
        CURATED (str): Read by hand from the launch announcement cited in the launch dates catalogue
            (`data/curated/launches.json`).
    """

    PAGE_MODIFIED = "page-modified"
    PAGE_PUBLISHED = "page-published"
    CATALOGUE_ENTRY = "catalogue-entry"
    WEBSITE_RECORD = "website-record"
    ASSUMED_TIMEZONE = "assumed-timezone"
    YEAR_ONLY = "year-only"
    OLDEST_VERSION = "oldest-version"
    FIRST_ANNOUNCEMENT = "first-announcement"
    FEED_START = "feed-start"
    CURATED = "curated"


@unique
class LaunchPrecision(StrEnum):
    """Enums representing how precise a curated launch date is.

    Attributes:
        DAY (str): The day of the launch is known.
        MONTH (str): Only its month is known, the date is the 1st of that month.
        YEAR (str): Only its year is known, the date is the 1st of January of that year.
    """

    DAY = "day"
    MONTH = "month"
    YEAR = "year"


@unique
class MarketRegion(StrEnum):
    """Enums representing the regions of the cloud market statistics.

    Attributes:
        WORLDWIDE (str): The worldwide market.
        EUROPE (str): The European market.
    """

    WORLDWIDE = "worldwide"
    EUROPE = "europe"


@unique
class MarketSegment(StrEnum):
    """Enums representing the segments of the cloud market statistics.

    Attributes:
        CLOUD_INFRASTRUCTURE (str): Cloud infrastructure services: IaaS, PaaS and hosted private cloud.
        PUBLIC_IAAS_PAAS (str): Public IaaS and PaaS services only.
    """

    CLOUD_INFRASTRUCTURE = "cloud-infrastructure-services"
    PUBLIC_IAAS_PAAS = "public-iaas-paas"


@unique
class MarketPlayer(StrEnum):
    """Enums representing the players of the cloud market statistics: providers and aggregates.

    Attributes:
        AMAZON (str): Amazon (Amazon Web Services).
        MICROSOFT (str): Microsoft (Azure).
        GOOGLE (str): Google (Google Cloud).
        BIG_THREE (str): Amazon, Microsoft and Google together.
        EUROPEAN_PROVIDERS (str): The European cloud providers together.
        SAP (str): SAP.
        DEUTSCHE_TELEKOM (str): Deutsche Telekom (T Cloud).
        NEOCLOUDS (str): The neoclouds together (CoreWeave, Nebius, Crusoe...).
        OTHERS (str): Every other provider: computed, not published.
        ALIBABA (str): Alibaba (Alibaba Cloud).
        IBM (str): IBM (IBM Cloud).
        ORACLE (str): Oracle (Oracle Cloud).
        HUAWEI (str): Huawei (Huawei Cloud).
        TENCENT (str): Tencent (Tencent Cloud).
    """

    AMAZON = "amazon"
    MICROSOFT = "microsoft"
    GOOGLE = "google"
    BIG_THREE = "big-three"
    EUROPEAN_PROVIDERS = "european-providers"
    SAP = "sap"
    DEUTSCHE_TELEKOM = "deutsche-telekom"
    NEOCLOUDS = "neoclouds"
    OTHERS = "others"
    ALIBABA = "alibaba"
    IBM = "ibm"
    ORACLE = "oracle"
    HUAWEI = "huawei"
    TENCENT = "tencent"

    @property
    def provider(self) -> Optional[CloudProvider]:
        """Get the cloud provider of the player, when it is one of the crawled providers.

        Returns:
            Optional[CloudProvider]: The cloud provider, `None` for an aggregate or a provider not crawled.
        """
        return PLAYER_PROVIDERS.get(self)

    @property
    def bloc(self) -> GeoBloc:
        """Get the geopolitical bloc of the player, `OTHER` for the aggregates spanning several blocs.

        Returns:
            GeoBloc: The bloc.
        """
        return PLAYER_BLOCS[self]


@unique
class UrlScheme(StrEnum):
    """Enums representing the schemes of the page addresses kept for the products and software.

    Attributes:
        HTTP (str): A plain HTTP page.
        HTTPS (str): A secure HTTP page.
    """

    HTTP = "http"
    HTTPS = "https"


@unique
class PriceUnit(StrEnum):
    """Enums representing the normalized unit a price is per, whatever unit the provider writes.

    Attributes:
        HOUR (str): An hour of use (an instance, a node, a cluster).
        SECOND (str): A second of use.
        MONTH (str): A month of use (a subscription, a reserved resource, a license).
        GIB (str): A gibibyte transferred or processed.
        GIB_MONTH (str): A gibibyte stored for a month.
        GIB_HOUR (str): A gibibyte of memory for an hour.
        VCPU_HOUR (str): A virtual CPU for an hour.
        VCPU_SECOND (str): A virtual CPU for a second (serverless).
        GIB_SECOND (str): A gibibyte of memory for a second (serverless).
        REQUEST (str): A request, call, invocation or operation.
        UNIT (str): A unit with no time (a certificate, an address, a domain, a message).
        UNIT_MONTH (str): A unit for a month (a user, a seat, an address, a node).
        UNIT_HOUR (str): A unit for an hour (an address, a load balancer, a gateway).
        TOKEN (str): A token of a language model.
        IMAGE (str): An image processed or generated.
        MINUTE (str): A minute (of audio, video, build).
        CHARACTER (str): A character (translation, speech).
        OTHER (str): A unit no other member names (its raw form is kept beside it).
        YEAR (str): A year of use (a domain, a yearly subscription).
        ONE_TIME (str): A one-time charge (a setup fee, a registration).
    """

    HOUR = "hour"
    SECOND = "second"
    MONTH = "month"
    GIB = "gib"
    GIB_MONTH = "gib-month"
    GIB_HOUR = "gib-hour"
    VCPU_HOUR = "vcpu-hour"
    VCPU_SECOND = "vcpu-second"
    GIB_SECOND = "gib-second"
    REQUEST = "request"
    UNIT = "unit"
    UNIT_MONTH = "unit-month"
    UNIT_HOUR = "unit-hour"
    TOKEN = "token"
    IMAGE = "image"
    MINUTE = "minute"
    CHARACTER = "character"
    OTHER = "other"
    YEAR = "year"
    ONE_TIME = "one-time"


@unique
class PriceModel(StrEnum):
    """Enums representing how a price is charged, or why a service has none.

    Attributes:
        ON_DEMAND (str): Pay as you go, without commitment.
        SPOT (str): Spare capacity, interruptible.
        RESERVED (str): A reserved instance or capacity, for a term.
        SAVINGS_PLAN (str): A spend commitment, for a term.
        COMMITMENT (str): Another committed use (a committed-use discount, a prepaid package).
        FREE (str): Free of charge (an always-free service, or the free tier of a priced one).
        QUOTE (str): Priced on request only (contact sales): no public price.
        INCLUDED (str): Included in another service, never charged apart.
        NOT_PUBLIC (str): A public service whose price is not published anywhere readable.
    """

    ON_DEMAND = "on-demand"
    SPOT = "spot"
    RESERVED = "reserved"
    SAVINGS_PLAN = "savings-plan"
    COMMITMENT = "commitment"
    FREE = "free"
    QUOTE = "quote"
    INCLUDED = "included"
    NOT_PUBLIC = "not-public"


@unique
class PriceTerm(StrEnum):
    """Enums representing the commitment term of a price.

    Attributes:
        NONE (str): No commitment.
        MONTH (str): A monthly commitment.
        ONE_YEAR (str): A one-year term.
        THREE_YEARS (str): A three-year term.
        FIVE_YEARS (str): A five-year term.
        THREE_MONTHS (str): A three-month term.
        SIX_MONTHS (str): A six-month term.
        TWO_YEARS (str): A two-year term.
        FOUR_YEARS (str): A four-year term.
        TEN_YEARS (str): A ten-year term.
        SIX_YEARS (str): A six-year term.
    """

    NONE = "none"
    MONTH = "1m"
    ONE_YEAR = "1y"
    THREE_YEARS = "3y"
    FIVE_YEARS = "5y"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    TWO_YEARS = "2y"
    FOUR_YEARS = "4y"
    TEN_YEARS = "10y"
    SIX_YEARS = "6y"


@unique
class FreeTierKind(StrEnum):
    """Enums representing the kinds of free offers of a provider.

    Attributes:
        ALWAYS_FREE (str): Free within a limit, for every account and without end.
        TRIAL_MONTHS (str): Free within a limit, for the first months of an account.
        CREDIT (str): A credit offered to a new account.
        TRIAL_DAYS (str): Free for the first days of an account or of a service.
    """

    ALWAYS_FREE = "always-free"
    TRIAL_MONTHS = "trial-months"
    CREDIT = "credit"
    TRIAL_DAYS = "trial-days"


@unique
class PriceSourceKind(StrEnum):
    """Enums representing what a price was read from (the fallback chain of the price crawls).

    Attributes:
        API (str): A public price API.
        CALCULATOR (str): The data a price calculator of the provider loads.
        PAGE (str): A pricing page.
        DOCS (str): A pricing section of the documentation.
        DOCUMENT (str): An official price list document (PDF, spreadsheet).
        ARCHIVE (str): A Wayback Machine capture of a pricing page (its live page unreachable).
        USER (str): Typed by a person.
    """

    API = "api"
    CALCULATOR = "calculator"
    PAGE = "page"
    DOCS = "docs"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    USER = "user"


@unique
class PriceOrigin(StrEnum):
    """Enums representing who wrote a stored price or free tier.

    Attributes:
        CRAWLER (str): A price crawl (replaced by the next crawl when it changes).
        USER (str): A person, in the explorer (never replaced by a crawl).
    """

    CRAWLER = "crawler"
    USER = "user"


@unique
class PriceSourceStatus(StrEnum):
    """Enums representing the outcome of the last read of a price source.

    Attributes:
        FETCHED (str): Read, its prices streamed.
        UNCHANGED (str): Unchanged since the last read (version, `ETag` or `Last-Modified`): not read again.
        FAILED (str): Not readable (an HTTP error, a refusal): its prices are left as they are.
    """

    FETCHED = "fetched"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@unique
class PriceFactKind(StrEnum):
    """Enums representing the kind of a fact streamed by a price crawl (the `kind` key of the item).

    Attributes:
        PRICE (str): A price of a service (`ServicePrice`).
        FREE_TIER (str): A free offer (`FreeTier`).
    """

    PRICE = "price"
    FREE_TIER = "free-tier"


PROVIDER_COUNTRIES: Final[Dict[CloudProvider, Country]] = {
    CloudProvider.AWS: Country.UNITED_STATES,
    CloudProvider.AZURE: Country.UNITED_STATES,
    CloudProvider.GCP: Country.UNITED_STATES,
    CloudProvider.IBM: Country.UNITED_STATES,
    CloudProvider.ORACLE: Country.UNITED_STATES,
    CloudProvider.OVH: Country.FRANCE,
    CloudProvider.SCALEWAY: Country.FRANCE,
    CloudProvider.COMBELL: Country.BELGIUM,
    CloudProvider.PROXIMUS: Country.BELGIUM,
    CloudProvider.STACKIT: Country.GERMANY,
    CloudProvider.TCLOUD: Country.GERMANY,
    CloudProvider.ARUBA: Country.ITALY,
    CloudProvider.SEEWEB: Country.ITALY,
    CloudProvider.GCORE: Country.LUXEMBOURG,
    CloudProvider.DEEP: Country.LUXEMBOURG,
    CloudProvider.ARSYS: Country.SPAIN,
    CloudProvider.GIGAS: Country.SPAIN,
    CloudProvider.EXOSCALE: Country.SWITZERLAND,
    CloudProvider.INFOMANIAK: Country.SWITZERLAND,
    CloudProvider.CIVO: Country.UNITED_KINGDOM,
    CloudProvider.KRYSTAL: Country.UNITED_KINGDOM,
    CloudProvider.ALIBABA: Country.CHINA,
    CloudProvider.HUAWEI: Country.CHINA,
    CloudProvider.TENCENT: Country.CHINA,
    CloudProvider.BAIDU: Country.CHINA,
    CloudProvider.VOLCENGINE: Country.CHINA,
    CloudProvider.CTYUN: Country.CHINA,
    CloudProvider.ECLOUD: Country.CHINA,
    CloudProvider.YANDEX_CLOUD: Country.RUSSIA,
    CloudProvider.VK_CLOUD: Country.RUSSIA,
    CloudProvider.CLOUD_RU: Country.RUSSIA,
    CloudProvider.SELECTEL: Country.RUSSIA,
}

PLAYER_PROVIDERS: Final[Dict[MarketPlayer, CloudProvider]] = {
    MarketPlayer.AMAZON: CloudProvider.AWS,
    MarketPlayer.MICROSOFT: CloudProvider.AZURE,
    MarketPlayer.GOOGLE: CloudProvider.GCP,
    MarketPlayer.DEUTSCHE_TELEKOM: CloudProvider.TCLOUD,
    MarketPlayer.ALIBABA: CloudProvider.ALIBABA,
    MarketPlayer.IBM: CloudProvider.IBM,
    MarketPlayer.ORACLE: CloudProvider.ORACLE,
    MarketPlayer.HUAWEI: CloudProvider.HUAWEI,
    MarketPlayer.TENCENT: CloudProvider.TENCENT,
}

COUNTRY_BLOCS: Final[Dict[Country, GeoBloc]] = {
    Country.UNITED_STATES: GeoBloc.UNITED_STATES,
    Country.FRANCE: GeoBloc.EUROPEAN_UNION,
    Country.BELGIUM: GeoBloc.EUROPEAN_UNION,
    Country.GERMANY: GeoBloc.EUROPEAN_UNION,
    Country.ITALY: GeoBloc.EUROPEAN_UNION,
    Country.LUXEMBOURG: GeoBloc.EUROPEAN_UNION,
    Country.SPAIN: GeoBloc.EUROPEAN_UNION,
    Country.SWITZERLAND: GeoBloc.OTHER,
    Country.UNITED_KINGDOM: GeoBloc.OTHER,
    Country.CHINA: GeoBloc.CHINA,
    Country.RUSSIA: GeoBloc.RUSSIA,
}

PLAYER_BLOCS: Final[Dict[MarketPlayer, GeoBloc]] = {
    MarketPlayer.AMAZON: GeoBloc.UNITED_STATES,
    MarketPlayer.MICROSOFT: GeoBloc.UNITED_STATES,
    MarketPlayer.GOOGLE: GeoBloc.UNITED_STATES,
    MarketPlayer.BIG_THREE: GeoBloc.UNITED_STATES,
    MarketPlayer.EUROPEAN_PROVIDERS: GeoBloc.EUROPEAN_UNION,
    MarketPlayer.SAP: GeoBloc.EUROPEAN_UNION,
    MarketPlayer.DEUTSCHE_TELEKOM: GeoBloc.EUROPEAN_UNION,
    MarketPlayer.NEOCLOUDS: GeoBloc.OTHER,
    MarketPlayer.OTHERS: GeoBloc.OTHER,
    MarketPlayer.ALIBABA: GeoBloc.CHINA,
    MarketPlayer.IBM: GeoBloc.UNITED_STATES,
    MarketPlayer.ORACLE: GeoBloc.UNITED_STATES,
    MarketPlayer.HUAWEI: GeoBloc.CHINA,
    MarketPlayer.TENCENT: GeoBloc.CHINA,
}
