from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ProviderMetric(StrEnum):
    """Enums representing the criteria and the targets measured per cloud provider and quarter.

    Attributes:
        PRODUCTS (str): The listed catalogue products.
        DOMAINS (str): The taxonomy domains the catalogue covers.
        CATEGORIES (str): The taxonomy categories the catalogue covers.
        AI_SHARE (str): The share of the products filed under the AI and machine learning domain.
        DATA_SHARE (str): The share of the products filed under the databases or data and analytics domains.
        SECURITY_SHARE (str): The share of the products filed under the security or identity domains.
        COMPUTE_SHARE (str): The share of the products filed under the compute or container domains.
        DEVELOPER_SHARE (str): The share of the products meant for developers (developer tools).
        LAUNCHES (str): The products added in the quarter (the website dates).
        DELETIONS (str): The products deleted in the quarter.
        MARKETPLACE_SIZE (str): The listed marketplace software.
        PUBLISHERS (str): The distinct publishers of the listed marketplace software.
        NEW_LISTINGS (str): The marketplace software added in the quarter.
        SAAS_SHARE (str): The share of the marketplace software delivered as SaaS.
        VM_SHARE (str): The share of the marketplace software delivered as virtual machine images.
        AI_MODEL_SHARE (str): The share of the marketplace software delivered as AI models.
        PARITY (str): The share of the products with an equivalent at AWS, Azure or Google Cloud.
        MENTIONS (str): The Synergy Research Group articles of the quarter naming the provider.
        MARKET_SHARE (str): The share of the world cloud infrastructure market (Synergy Research Group).
        REVENUE (str): The cloud infrastructure revenue: the market share times the market size.
        CLOUD_REVENUE (str): The cloud revenue an annual report or an analyst publishes.
        CAPEX (str): The capital expenditure (data centres, servers).
        REGIONS (str): The cloud regions.
        AVAILABILITY_ZONES (str): The availability zones.
        COUNTRIES_SERVED (str): The countries holding a region.
        NETWORK_EXCHANGES (str): The internet exchanges the provider peers at (PeeringDB).
        FACILITIES (str): The interconnection facilities the provider is present at (PeeringDB).
        GPU_CLUSTERS (str): The large GPU clusters the provider operates.
        CERTIFICATIONS (str): The sovereignty and compliance certifications held (FedRAMP, SecNumCloud, C5…).
        SDK_STARS (str): The GitHub stars of the provider's SDKs and Terraform provider.
        EMPLOYEES (str): The employees of the provider (or of its group).
        AGE (str): The years since the provider was founded.
    """

    PRODUCTS = "products"
    DOMAINS = "domains"
    CATEGORIES = "categories"
    AI_SHARE = "ai-share"
    DATA_SHARE = "data-share"
    SECURITY_SHARE = "security-share"
    COMPUTE_SHARE = "compute-share"
    DEVELOPER_SHARE = "developer-share"
    LAUNCHES = "launches"
    DELETIONS = "deletions"
    MARKETPLACE_SIZE = "marketplace-size"
    PUBLISHERS = "publishers"
    NEW_LISTINGS = "new-listings"
    SAAS_SHARE = "saas-share"
    VM_SHARE = "vm-share"
    AI_MODEL_SHARE = "ai-model-share"
    PARITY = "parity"
    MENTIONS = "mentions"
    MARKET_SHARE = "market-share"
    REVENUE = "revenue"
    CLOUD_REVENUE = "cloud-revenue"
    CAPEX = "capex"
    REGIONS = "regions"
    AVAILABILITY_ZONES = "availability-zones"
    COUNTRIES_SERVED = "countries-served"
    NETWORK_EXCHANGES = "network-exchanges"
    FACILITIES = "facilities"
    GPU_CLUSTERS = "gpu-clusters"
    CERTIFICATIONS = "certifications"
    SDK_STARS = "sdk-stars"
    EMPLOYEES = "employees"
    AGE = "age"


@unique
class MetricSource(StrEnum):
    """Enums representing where a measure of a provider comes from.

    Attributes:
        DERIVED (str): Computed from the crawled catalogues and marketplaces.
        SYNERGY (str): The Synergy Research Group articles.
        EDGAR (str): The SEC EDGAR financial statements (XBRL).
        WIKIDATA (str): Wikidata.
        PEERINGDB (str): PeeringDB.
        GITHUB (str): GitHub.
        MANUAL (str): Typed in from an annual report or an analyst publication (`conf/metrics/manual-metrics.yaml`).
    """

    DERIVED = "derived"
    SYNERGY = "synergy"
    EDGAR = "edgar"
    WIKIDATA = "wikidata"
    PEERINGDB = "peeringdb"
    GITHUB = "github"
    MANUAL = "manual"


@unique
class MetricFamily(StrEnum):
    """Enums representing the families of the criteria, as the guide groups them.

    Attributes:
        ECONOMIC (str): Revenue and market share (the economic targets).
        BREADTH (str): How much the catalogue covers.
        MIX (str): What the catalogue is made of.
        VELOCITY (str): How fast the catalogue changes.
        ECOSYSTEM (str): The marketplace and its publishers.
        PARITY (str): How much of the leaders' offer the provider matches.
        VISIBILITY (str): How often the analysts name the provider.
        CAPACITY (str): Infrastructure: capital expenditure, regions, GPU clusters.
        NETWORK (str): Interconnection.
        TRUST (str): Certifications.
        ADOPTION (str): Developer adoption.
        COMPANY (str): Company facts.
    """

    ECONOMIC = "economic"
    BREADTH = "breadth"
    MIX = "mix"
    VELOCITY = "velocity"
    ECOSYSTEM = "ecosystem"
    PARITY = "parity"
    VISIBILITY = "visibility"
    CAPACITY = "capacity"
    NETWORK = "network"
    TRUST = "trust"
    ADOPTION = "adoption"
    COMPANY = "company"


@unique
class MetricScale(StrEnum):
    """Enums representing how a measure is transformed before the statistics.

    Attributes:
        COUNT (str): A count: `log(1 + x)`.
        AMOUNT (str): An amount (billions, people): `log(x)`, zero and negative values left out.
        SHARE (str): A share from 0 to 1, or a percent: used as it is.
    """

    COUNT = "count"
    AMOUNT = "amount"
    SHARE = "share"


@unique
class DriverScope(StrEnum):
    """Enums representing which observations a driver analysis uses.

    Attributes:
        CROSS_SECTION (str): One observation per provider: its latest quarter holding every measure.
        PANEL (str): One observation per provider and quarter: the changes from one year to the next.
    """

    CROSS_SECTION = "cross-section"
    PANEL = "panel"


@unique
class DriverRole(StrEnum):
    """Enums representing the role a parameter plays in a driver analysis.

    Attributes:
        TARGET (str): The measure of the rise, explained by the criteria.
        CRITERION (str): A candidate driver of the rise.
        CONTROL (str): A measure held constant in the partial correlations (e.g. the size).
        SCOPE (str): Which observations are used: the latest quarter, or every quarter (panel).
        LAG (str): How many quarters the criteria lead the target (panel only).
    """

    TARGET = "target"
    CRITERION = "criterion"
    CONTROL = "control"
    SCOPE = "scope"
    LAG = "lag"


@unique
class WarningSeverity(StrEnum):
    """Enums representing how much a warning limits the conclusions of a driver analysis.

    Attributes:
        INFO (str): Something was left out, the rest stands.
        CAUTION (str): The results stand, but read them with care.
        BLOCKING (str): A part of the analysis could not run.
    """

    INFO = "info"
    CAUTION = "caution"
    BLOCKING = "blocking"


@unique
class DriverWarningKind(StrEnum):
    """Enums representing what limits the conclusions of a driver analysis.

    Attributes:
        FEW_PROVIDERS (str): Too few providers measure the target to tell a criterion from a provider.
        FEW_OBSERVATIONS (str): Too few complete observations: the results are fragile.
        MISSING_VALUES (str): Observations miss a criterion and are left out of the regression.
        UNCORRELATABLE (str): A criterion has fewer than 3 observations with the target, or is constant.
        NOTHING_CORRELATED (str): No criterion can be correlated with the target.
        LEFT_OUT (str): Criteria not correlated with the target are left out of the regression.
        CONSTANT (str): Criteria constant over the observations are left out of the regression.
        TOO_MANY_CRITERIA (str): Only the criteria most correlated with the target are regressed.
        REGRESSION_SKIPPED (str): Too few observations for the criteria: no regression.
        UNSTABLE (str): Fewer than about 10 observations per criterion: the coefficients are unstable.
        COLLINEAR (str): Criteria moving together: their coefficients are unstable.
        SHORT_PANEL (str): The panel holds too few providers or quarters.
    """

    FEW_PROVIDERS = "few-providers"
    FEW_OBSERVATIONS = "few-observations"
    MISSING_VALUES = "missing-values"
    UNCORRELATABLE = "uncorrelatable"
    NOTHING_CORRELATED = "nothing-correlated"
    LEFT_OUT = "left-out"
    CONSTANT = "constant"
    TOO_MANY_CRITERIA = "too-many-criteria"
    REGRESSION_SKIPPED = "regression-skipped"
    UNSTABLE = "unstable"
    COLLINEAR = "collinear"
    SHORT_PANEL = "short-panel"


@unique
class DriverColumn(StrEnum):
    """Enums representing the columns of the table of the driver analysis.

    Attributes:
        CRITERION (str): The criterion.
        IMPORTANCE (str): Its share of the explained variance (Shapley split of the R²).
        BETA (str): Its standardized regression coefficient.
        BETA_INTERVAL (str): The 95% interval of the coefficient.
        BETA_P (str): The p-value of the coefficient.
        RHO (str): Its Spearman correlation with the target.
        RHO_Q (str): The Benjamini-Hochberg q-value of the correlation.
        PARTIAL (str): The correlation once the controls are held constant.
        OBSERVATIONS (str): The observations holding the criterion and the target.
        GRANGER (str): The p-value of the test that the criterion leads the target (panel only).
    """

    CRITERION = "criterion"
    IMPORTANCE = "importance"
    BETA = "beta"
    BETA_INTERVAL = "beta-interval"
    BETA_P = "beta-p"
    RHO = "rho"
    RHO_Q = "rho-q"
    PARTIAL = "partial"
    OBSERVATIONS = "observations"
    GRANGER = "granger"
