from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class SynergyPlayerName(StrEnum):
    """Enums representing the market player names matched in the Synergy Research Group press releases.

    Attributes:
        ALIBABA (str): Alibaba.
        ORACLE (str): Oracle.
        SALESFORCE (str): Salesforce.
        IBM (str): IBM.
        HUAWEI (str): Huawei.
        TENCENT (str): Tencent.
        BAIDU (str): Baidu.
        CHINA_TELECOM (str): China Telecom.
        CHINA_MOBILE (str): China Mobile.
        CHINA_UNICOM (str): China Unicom.
        RACKSPACE (str): Rackspace.
        SNOWFLAKE (str): Snowflake.
        MONGODB (str): MongoDB.
        VMWARE (str): VMware.
        COREWEAVE (str): CoreWeave.
        NEBIUS (str): Nebius.
        CRUSOE (str): Crusoe.
        LAMBDA (str): Lambda.
        OPENAI (str): OpenAI.
        ANTHROPIC (str): Anthropic.
        DATABRICKS (str): Databricks.
        NSCALE (str): Nscale.
        OVHCLOUD (str): OVHcloud.
        ORANGE (str): Orange.
        TELECOM_ITALIA (str): Telecom Italia.
        DEUTSCHE_TELEKOM (str): Deutsche Telekom.
        SAP (str): SAP.
        IONOS (str): IONOS.
        SCALEWAY (str): Scaleway.
        HETZNER (str): Hetzner.
        YANDEX (str): Yandex.
        AMAZON (str): Amazon.
        AWS (str): Amazon Web Services, the cloud of Amazon.
        MICROSOFT (str): Microsoft.
        AZURE (str): Azure, the cloud of Microsoft.
        GOOGLE (str): Google.
    """

    ALIBABA = "Alibaba"
    ORACLE = "Oracle"
    SALESFORCE = "Salesforce"
    IBM = "IBM"
    HUAWEI = "Huawei"
    TENCENT = "Tencent"
    BAIDU = "Baidu"
    CHINA_TELECOM = "China Telecom"
    CHINA_MOBILE = "China Mobile"
    CHINA_UNICOM = "China Unicom"
    RACKSPACE = "Rackspace"
    SNOWFLAKE = "Snowflake"
    MONGODB = "MongoDB"
    VMWARE = "VMware"
    COREWEAVE = "CoreWeave"
    NEBIUS = "Nebius"
    CRUSOE = "Crusoe"
    LAMBDA = "Lambda"
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    DATABRICKS = "Databricks"
    NSCALE = "Nscale"
    OVHCLOUD = "OVHcloud"
    ORANGE = "Orange"
    TELECOM_ITALIA = "Telecom Italia"
    DEUTSCHE_TELEKOM = "Deutsche Telekom"
    SAP = "SAP"
    IONOS = "IONOS"
    SCALEWAY = "Scaleway"
    HETZNER = "Hetzner"
    YANDEX = "Yandex"
    AMAZON = "Amazon"
    AWS = "AWS"
    MICROSOFT = "Microsoft"
    AZURE = "Azure"
    GOOGLE = "Google"


@unique
class SynergyOrdinal(StrEnum):
    """Enums representing the ordinal words of the ranks and of the quarters or half-years in the press releases.

    Attributes:
        FIRST (str): First.
        SECOND (str): Second.
        THIRD (str): Third.
        FOURTH (str): Fourth.
        FIFTH (str): Fifth.
        SIXTH (str): Sixth.
        SEVENTH (str): Seventh.
        EIGHTH (str): Eighth.
        NINTH (str): Ninth.
        TENTH (str): Tenth.
    """

    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    FOURTH = "fourth"
    FIFTH = "fifth"
    SIXTH = "sixth"
    SEVENTH = "seventh"
    EIGHTH = "eighth"
    NINTH = "ninth"
    TENTH = "tenth"


@unique
class SynergyPatternGroup(StrEnum):
    """Enums representing the named groups of the Synergy Research Group press release patterns.

    Attributes:
        QUALIFIER (str): The wording of an approximate figure, e.g. `around`.
        LOW (str): A share, or the low end of a share band.
        HIGH (str): The high end of a share band.
        VALUE (str): A market size, in billions.
        FIRST (str): The first share listed by position.
        SECOND (str): The second share listed by position.
        THIRD (str): The third share listed by position.
        LATER (str): The later share of the European providers.
        LATER_QUALIFIER (str): The wording of an approximate later share of the European providers.
        NAMES (str): The names of the leading European providers.
        QUARTER (str): The ordinal word of a quarter.
        HALF (str): The ordinal word of a half-year.
        YEAR (str): A year.
    """

    QUALIFIER = "qualifier"
    LOW = "low"
    HIGH = "high"
    VALUE = "value"
    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    LATER = "later"
    LATER_QUALIFIER = "later_qualifier"
    NAMES = "names"
    QUARTER = "quarter"
    HALF = "half"
    YEAR = "year"


@unique
class SynergyCurrency(StrEnum):
    """Enums representing the currencies of the amounts given by the Synergy Research Group press releases.

    Attributes:
        EURO (str): The euro, the currency of the European market figures.
    """

    EURO = "EUR"
