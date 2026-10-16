from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique
from typing import Dict, Final, Optional


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

    @property
    def country(self) -> Country:
        """Get the country of the cloud provider, where it is headquartered.

        Returns:
            Country: The country.
        """
        return PROVIDER_COUNTRIES[self]


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
class SoftwareType(StrEnum):
    """Enums representing the kind of a marketplace software.

    Attributes:
        ATS (str): Applicant tracking systems: recruitment, talent acquisition.
        CRM (str): Customer relationship management.
        ERP (str): Enterprise resource planning.
        HRIS (str): Human resources: HR management, payroll, talent management.
        ACCOUNTING (str): Accounting and finance: billing, invoicing, expenses, tax.
        ECOMMERCE (str): E-commerce: online stores, payments, point of sale.
        CMS (str): Content management: website builders, blogs, portals.
        MARKETING (str): Marketing: automation, advertising, SEO, social media.
        CUSTOMER_SERVICE (str): Customer service: help desks, contact centers, chatbots.
        COLLABORATION (str): Collaboration and productivity: office suites, file sharing, whiteboards.
        COMMUNICATION (str): Communication: email, chat, video conferencing, telephony.
        PROJECT_MANAGEMENT (str): Project and task management.
        DOCUMENT_MANAGEMENT (str): Document management: content repositories, e-signature, OCR.
        BUSINESS_INTELLIGENCE (str): Business intelligence: analytics, reporting, dashboards.
        SUPPLY_CHAIN (str): Supply chain: procurement, logistics, inventory, manufacturing.
        LEGAL_COMPLIANCE (str): Legal, governance, risk and compliance.
        E_LEARNING (str): E-learning: learning management systems, education.
        HEALTHCARE (str): Healthcare and life sciences.
        MEDIA (str): Media: video, streaming, image and audio processing.
        ITSM (str): IT service management: service desks, asset management.
        AI_ML (str): Artificial intelligence and machine learning: platforms, models, agents.
        DATABASE (str): Databases and caches.
        DATA_INTEGRATION (str): Data integration: ETL, pipelines, data platforms.
        DEVOPS (str): DevOps: CI/CD, source control, infrastructure as code.
        DEVELOPMENT (str): Development: IDEs, frameworks, runtimes, application stacks.
        LOW_CODE (str): Low-code and no-code application platforms, workflow automation.
        TESTING (str): Testing and quality assurance.
        MONITORING (str): Monitoring: observability, logs, APM.
        SECURITY (str): Security: firewalls, threat protection, vulnerability management.
        IDENTITY (str): Identity and access management, single sign-on.
        BACKUP (str): Backup and disaster recovery.
        STORAGE (str): Storage: file, object and block storage.
        NETWORKING (str): Networking: VPN, load balancing, SD-WAN, CDN.
        OPERATING_SYSTEM (str): Operating systems and virtual desktops.
        CONTAINER (str): Containers and Kubernetes management.
        MESSAGING (str): Messaging: queues, event streaming.
        API_MANAGEMENT (str): API management and gateways.
        IOT (str): Internet of things.
        BLOCKCHAIN (str): Blockchain.
        OTHER (str): Software of no recognized type.
    """

    ATS = "ats"
    CRM = "crm"
    ERP = "erp"
    HRIS = "hris"
    ACCOUNTING = "accounting"
    ECOMMERCE = "ecommerce"
    CMS = "cms"
    MARKETING = "marketing"
    CUSTOMER_SERVICE = "customer-service"
    COLLABORATION = "collaboration"
    COMMUNICATION = "communication"
    PROJECT_MANAGEMENT = "project-management"
    DOCUMENT_MANAGEMENT = "document-management"
    BUSINESS_INTELLIGENCE = "business-intelligence"
    SUPPLY_CHAIN = "supply-chain"
    LEGAL_COMPLIANCE = "legal-compliance"
    E_LEARNING = "e-learning"
    HEALTHCARE = "healthcare"
    MEDIA = "media"
    ITSM = "itsm"
    AI_ML = "ai-ml"
    DATABASE = "database"
    DATA_INTEGRATION = "data-integration"
    DEVOPS = "devops"
    DEVELOPMENT = "development"
    LOW_CODE = "low-code"
    TESTING = "testing"
    MONITORING = "monitoring"
    SECURITY = "security"
    IDENTITY = "identity"
    BACKUP = "backup"
    STORAGE = "storage"
    NETWORKING = "networking"
    OPERATING_SYSTEM = "operating-system"
    CONTAINER = "container"
    MESSAGING = "messaging"
    API_MANAGEMENT = "api-management"
    IOT = "iot"
    BLOCKCHAIN = "blockchain"
    OTHER = "other"


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
}

PLAYER_PROVIDERS: Final[Dict[MarketPlayer, CloudProvider]] = {
    MarketPlayer.AMAZON: CloudProvider.AWS,
    MarketPlayer.MICROSOFT: CloudProvider.AZURE,
    MarketPlayer.GOOGLE: CloudProvider.GCP,
    MarketPlayer.DEUTSCHE_TELEKOM: CloudProvider.TCLOUD,
}
