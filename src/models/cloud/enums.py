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
    """

    PAGE_MODIFIED = "page-modified"
    PAGE_PUBLISHED = "page-published"
    CATALOGUE_ENTRY = "catalogue-entry"
    WEBSITE_RECORD = "website-record"
    ASSUMED_TIMEZONE = "assumed-timezone"
    YEAR_ONLY = "year-only"
    OLDEST_VERSION = "oldest-version"


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
}
