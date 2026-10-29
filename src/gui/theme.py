from __future__ import annotations

# Standard Library Imports.
import logging
from datetime import datetime
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication

# First Party Imports.
from gui.flags.flag_painter import FlagPainter
from models.cloud.dated_item import DatedItem
from models.cloud.enums import (
    CloudProvider,
    Country,
    DateCaveat,
    DateSource,
    DeliveryMethod,
    GeoBloc,
    MarketPlayer,
    MarketRegion,
    MarketSegment,
    SoftwareAudience,
    SoftwareCategory,
)
from models.correspondence.enums import CardinalityClass
from models.drivers.enums import DriverRole, WarningSeverity
from models.history.catalog.company import Company


class Theme:
    """Dark, colourized look of the application: palette, stylesheet, provider, country and log level colours.

    Attributes:
        WINDOW (ClassVar[str]): The window background colour.
        SURFACE (ClassVar[str]): The panels background colour.
        SURFACE_ALT (ClassVar[str]): The raised elements background colour.
        BORDER (ClassVar[str]): The borders colour.
        TEXT (ClassVar[str]): The main text colour.
        TEXT_MUTED (ClassVar[str]): The secondary text colour.
        ACCENT (ClassVar[str]): The selection and focus colour.
        ACCENT_ALT (ClassVar[str]): The secondary accent colour, e.g. the amounts in euros.
        PROVIDER_COLORS (ClassVar[Dict[CloudProvider, str]]): The accent colour of each cloud provider.
        PROVIDER_LABELS (ClassVar[Dict[CloudProvider, str]]): The display name of each cloud provider.
        PROVIDER_SHORT_LABELS (ClassVar[Dict[CloudProvider, str]]): The short display name of each cloud provider.
        COUNTRY_LABELS (ClassVar[Dict[Country, str]]): The display name of each cloud provider country.
        CATEGORY_LABELS (ClassVar[Dict[SoftwareCategory, str]]): The display name of each software category.
        CATEGORY_COLORS (ClassVar[Dict[SoftwareCategory, str]]): The colour of each software category.
        AUDIENCE_LABELS (ClassVar[Dict[SoftwareAudience, str]]): The display name of each software audience.
        AUDIENCE_COLORS (ClassVar[Dict[SoftwareAudience, str]]): The colour of each software audience (both: a mix of
            the two category colours).
        UI_FONT_SIZE (ClassVar[int]): The text size of the controls, tables and panels, in pixels (compact, so that
            the charts get the room).
        CHART_FONT_SIZE (ClassVar[int]): The text size of the charts and diagrams, in pixels (kept larger).
        CHART_WIDGETS (ClassVar[Tuple[str, ...]]): The painted chart and diagram widgets keeping `CHART_FONT_SIZE`.
        CORRESPONDENCE_FILLS (ClassVar[Dict[CardinalityClass, str]]): The fill of the service pills of each
            correspondence class, light for 1:1, darker as one side holds more services.
        CORRESPONDENCE_INKS (ClassVar[Dict[CardinalityClass, str]]): The text colour on each pill fill.
        CORRESPONDENCE_EDGES (ClassVar[Dict[CardinalityClass, str]]): The connector colour of each class (brighter as
            the class grows, readable on the dark surfaces).
        CORRESPONDENCE_LABELS (ClassVar[Dict[CardinalityClass, str]]): The legend of each class.
        DELIVERY_LABELS (ClassVar[Dict[DeliveryMethod, str]]): The display name of each delivery method.
        REGION_LABELS (ClassVar[Dict[MarketRegion, str]]): The display name of each market region.
        SEGMENT_LABELS (ClassVar[Dict[MarketSegment, str]]): The display name of each market segment.
        PLAYER_LABELS (ClassVar[Dict[MarketPlayer, str]]): The display name of each market player.
        PLAYER_COLORS (ClassVar[Dict[MarketPlayer, str]]): The colour of the market players which are not crawled
            providers (the others take their provider colour).
        BLOC_LABELS (ClassVar[Dict[GeoBloc, str]]): The display name of each geopolitical bloc.
        BLOC_COLORS (ClassVar[Dict[GeoBloc, str]]): The colour of each geopolitical bloc (Okabe-Ito, colour-blind
            safe).
        LEVEL_COLORS (ClassVar[Dict[int, str]]): The colour of each log level.
        WARNING (ClassVar[str]): The colour of the warnings, e.g. the dates with a caveat.
        DRIVER_POSITIVE (ClassVar[str]): A criterion going with the rise (significant).
        DRIVER_NEGATIVE (ClassVar[str]): A criterion going against the rise (significant).
        DRIVER_FAINT (ClassVar[str]): A criterion whose correlation is not significant.
        DRIVER_ROLE_COLORS (ClassVar[Dict[DriverRole, str]]): The colour of each role of the driver analysis (the
            legend chips, the scatter axes). The criteria share the colour of the importance bars.
        WARNING_COLORS (ClassVar[Dict[WarningSeverity, str]]): The colour of each severity of the warnings.
        WARNING_SYMBOLS (ClassVar[Dict[WarningSeverity, str]]): The glyph drawn on the warnings of each severity.
        POLICY_SHOCK (ClassVar[str]): The colour of the notable-event markers, the policy-shock colour of mega-trends.
        CAVEAT_LABELS (ClassVar[Dict[DateCaveat, str]]): Why a date published by a website may be inaccurate.
        flags (FlagPainter): The painter of the country flags.
    """

    WINDOW: ClassVar[str] = "#11151c"
    SURFACE: ClassVar[str] = "#181d26"
    SURFACE_ALT: ClassVar[str] = "#212835"
    BORDER: ClassVar[str] = "#2c3442"
    TEXT: ClassVar[str] = "#e6e9ef"
    TEXT_MUTED: ClassVar[str] = "#9aa4b2"
    ACCENT: ClassVar[str] = "#4f8cff"
    ACCENT_ALT: ClassVar[str] = "#a77bf3"
    PROVIDER_COLORS: ClassVar[Dict[CloudProvider, str]] = {
        CloudProvider.AWS: "#ff9900",
        CloudProvider.AZURE: "#00a2ed",
        CloudProvider.GCP: "#34a853",
        CloudProvider.IBM: "#a6c8ff",
        CloudProvider.ORACLE: "#f2545b",
        CloudProvider.OVH: "#5c6cff",
        CloudProvider.SCALEWAY: "#b26bff",
        CloudProvider.COMBELL: "#ff6fb5",
        CloudProvider.PROXIMUS: "#9d8cff",
        CloudProvider.STACKIT: "#00c2a8",
        CloudProvider.TCLOUD: "#e20074",
        CloudProvider.ARUBA: "#e8a33d",
        CloudProvider.SEEWEB: "#4dd0e1",
        CloudProvider.GCORE: "#ff8a65",
        CloudProvider.DEEP: "#ffd23f",
        CloudProvider.ARSYS: "#7fd17f",
        CloudProvider.GIGAS: "#c5e1a5",
        CloudProvider.EXOSCALE: "#d9e021",
        CloudProvider.INFOMANIAK: "#3d8bfd",
        CloudProvider.CIVO: "#b0bec5",
        CloudProvider.KRYSTAL: "#ce93d8",
        CloudProvider.ALIBABA: "#ff6a00",
        CloudProvider.HUAWEI: "#e53935",
        CloudProvider.TENCENT: "#006eff",
        CloudProvider.BAIDU: "#e0e0e0",
        CloudProvider.VOLCENGINE: "#a1887f",
        CloudProvider.CTYUN: "#ffb74d",
        CloudProvider.ECLOUD: "#81d4fa",
        CloudProvider.YANDEX_CLOUD: "#fc3f1d",
        CloudProvider.VK_CLOUD: "#0077ff",
        CloudProvider.CLOUD_RU: "#26d07c",
        CloudProvider.SELECTEL: "#c62828",
    }
    PROVIDER_LABELS: ClassVar[Dict[CloudProvider, str]] = {
        CloudProvider.AWS: "Amazon Web Services",
        CloudProvider.AZURE: "Microsoft Azure",
        CloudProvider.GCP: "Google Cloud Platform",
        CloudProvider.IBM: "IBM Cloud",
        CloudProvider.ORACLE: "Oracle Cloud",
        CloudProvider.OVH: "OVHcloud",
        CloudProvider.SCALEWAY: "Scaleway",
        CloudProvider.COMBELL: "Combell",
        CloudProvider.PROXIMUS: "Proximus NXT",
        CloudProvider.STACKIT: "STACKIT",
        CloudProvider.TCLOUD: "T Cloud Public",
        CloudProvider.ARUBA: "Aruba Cloud",
        CloudProvider.SEEWEB: "Seeweb",
        CloudProvider.GCORE: "Gcore",
        CloudProvider.DEEP: "DEEP (POST Luxembourg)",
        CloudProvider.ARSYS: "Arsys",
        CloudProvider.GIGAS: "Gigas",
        CloudProvider.EXOSCALE: "Exoscale",
        CloudProvider.INFOMANIAK: "Infomaniak",
        CloudProvider.CIVO: "Civo",
        CloudProvider.KRYSTAL: "Krystal",
        CloudProvider.ALIBABA: "Alibaba Cloud",
        CloudProvider.HUAWEI: "Huawei Cloud",
        CloudProvider.TENCENT: "Tencent Cloud",
        CloudProvider.BAIDU: "Baidu AI Cloud",
        CloudProvider.VOLCENGINE: "Volcano Engine",
        CloudProvider.CTYUN: "China Telecom Cloud",
        CloudProvider.ECLOUD: "China Mobile Cloud",
        CloudProvider.YANDEX_CLOUD: "Yandex Cloud",
        CloudProvider.VK_CLOUD: "VK Cloud",
        CloudProvider.CLOUD_RU: "Cloud.ru",
        CloudProvider.SELECTEL: "Selectel",
    }
    PROVIDER_SHORT_LABELS: ClassVar[Dict[CloudProvider, str]] = {
        CloudProvider.AWS: "AWS",
        CloudProvider.AZURE: "Azure",
        CloudProvider.GCP: "GCP",
        CloudProvider.IBM: "IBM",
        CloudProvider.ORACLE: "Oracle",
        CloudProvider.OVH: "OVHcloud",
        CloudProvider.SCALEWAY: "Scaleway",
        CloudProvider.COMBELL: "Combell",
        CloudProvider.PROXIMUS: "Proximus",
        CloudProvider.STACKIT: "STACKIT",
        CloudProvider.TCLOUD: "T Cloud",
        CloudProvider.ARUBA: "Aruba",
        CloudProvider.SEEWEB: "Seeweb",
        CloudProvider.GCORE: "Gcore",
        CloudProvider.DEEP: "DEEP",
        CloudProvider.ARSYS: "Arsys",
        CloudProvider.GIGAS: "Gigas",
        CloudProvider.EXOSCALE: "Exoscale",
        CloudProvider.INFOMANIAK: "Infomaniak",
        CloudProvider.CIVO: "Civo",
        CloudProvider.KRYSTAL: "Krystal",
        CloudProvider.ALIBABA: "Alibaba",
        CloudProvider.HUAWEI: "Huawei",
        CloudProvider.TENCENT: "Tencent",
        CloudProvider.BAIDU: "Baidu",
        CloudProvider.VOLCENGINE: "Volcano",
        CloudProvider.CTYUN: "China Telecom",
        CloudProvider.ECLOUD: "China Mobile",
        CloudProvider.YANDEX_CLOUD: "Yandex",
        CloudProvider.VK_CLOUD: "VK Cloud",
        CloudProvider.CLOUD_RU: "Cloud.ru",
        CloudProvider.SELECTEL: "Selectel",
    }
    COUNTRY_LABELS: ClassVar[Dict[Country, str]] = {
        Country.UNITED_STATES: "United States",
        Country.FRANCE: "France",
        Country.BELGIUM: "Belgium",
        Country.GERMANY: "Germany",
        Country.ITALY: "Italy",
        Country.LUXEMBOURG: "Luxembourg",
        Country.SPAIN: "Spain",
        Country.SWITZERLAND: "Switzerland",
        Country.UNITED_KINGDOM: "United Kingdom",
        Country.CHINA: "China",
        Country.RUSSIA: "Russia",
    }
    CATEGORY_LABELS: ClassVar[Dict[SoftwareCategory, str]] = {
        SoftwareCategory.DEVELOPER_TOOL: "Developer tool",
        SoftwareCategory.END_USER_SOFTWARE: "End-user software",
    }
    CATEGORY_COLORS: ClassVar[Dict[SoftwareCategory, str]] = {
        SoftwareCategory.DEVELOPER_TOOL: "#4f8cff",
        SoftwareCategory.END_USER_SOFTWARE: "#3fb950",
    }
    AUDIENCE_LABELS: ClassVar[Dict[SoftwareAudience, str]] = {
        SoftwareAudience.DEVELOPER_TOOL: "Developer tool only",
        SoftwareAudience.END_USER_SOFTWARE: "End-user software only",
        SoftwareAudience.BOTH: "Both",
    }
    AUDIENCE_COLORS: ClassVar[Dict[SoftwareAudience, str]] = {
        SoftwareAudience.DEVELOPER_TOOL: "#4f8cff",
        SoftwareAudience.END_USER_SOFTWARE: "#3fb950",
        SoftwareAudience.BOTH: "#47a2a7",
    }
    UI_FONT_SIZE: ClassVar[int] = 12
    CHART_FONT_SIZE: ClassVar[int] = 13
    CHART_WIDGETS: ClassVar[Tuple[str, ...]] = (
        "MetricChart",
        "ShareBarChart",
        "MarketSizeChart",
        "ProviderBarChart",
        "DomainBarChart",
        "CorrespondenceDiagram",
        "DiagramHeader",
        "DiagramLegend",
        "CoverageMatrix",
        "DriverBarChart",
        "DriverScatterChart",
        "LeadershipChart",
        "TimeSeriesChart",
        "LagChart",
    )
    CORRESPONDENCE_FILLS: ClassVar[Dict[CardinalityClass, str]] = {
        CardinalityClass.ONE_TO_ONE: "#d3e2e6",
        CardinalityClass.TWO_TO_ONE: "#8fb4be",
        CardinalityClass.THREE_TO_ONE: "#2c6c7a",
        CardinalityClass.MANY_TO_ONE: "#0e2930",
        CardinalityClass.MISSING: "#212835",
    }
    CORRESPONDENCE_INKS: ClassVar[Dict[CardinalityClass, str]] = {
        CardinalityClass.ONE_TO_ONE: "#11151c",
        CardinalityClass.TWO_TO_ONE: "#11151c",
        CardinalityClass.THREE_TO_ONE: "#eef4f6",
        CardinalityClass.MANY_TO_ONE: "#eef4f6",
        CardinalityClass.MISSING: "#9aa4b2",
    }
    CORRESPONDENCE_EDGES: ClassVar[Dict[CardinalityClass, str]] = {
        CardinalityClass.ONE_TO_ONE: "#b5cfd6",
        CardinalityClass.TWO_TO_ONE: "#79b3c1",
        CardinalityClass.THREE_TO_ONE: "#3d9fb3",
        CardinalityClass.MANY_TO_ONE: "#4fd0e6",
        CardinalityClass.MISSING: "#4a5566",
    }
    CORRESPONDENCE_LABELS: ClassVar[Dict[CardinalityClass, str]] = {
        CardinalityClass.ONE_TO_ONE: "1:1 correspondence",
        CardinalityClass.TWO_TO_ONE: "2:1 correspondence",
        CardinalityClass.THREE_TO_ONE: "3:1 correspondence",
        CardinalityClass.MANY_TO_ONE: "n:1 correspondence",
        CardinalityClass.MISSING: "No equivalent",
    }
    DELIVERY_LABELS: ClassVar[Dict[DeliveryMethod, str]] = {
        DeliveryMethod.SAAS: "SaaS",
        DeliveryMethod.VIRTUAL_MACHINE: "Virtual machine",
        DeliveryMethod.CONTAINER: "Container",
        DeliveryMethod.KUBERNETES: "Kubernetes",
        DeliveryMethod.API: "API",
        DeliveryMethod.AI_MODEL: "AI model",
        DeliveryMethod.ONE_CLICK_APP: "One-click app",
        DeliveryMethod.DOWNLOAD: "Download",
        DeliveryMethod.OTHER: "Other",
    }
    REGION_LABELS: ClassVar[Dict[MarketRegion, str]] = {
        MarketRegion.WORLDWIDE: "Worldwide",
        MarketRegion.EUROPE: "Europe",
    }
    SEGMENT_LABELS: ClassVar[Dict[MarketSegment, str]] = {
        MarketSegment.CLOUD_INFRASTRUCTURE: "Cloud infrastructure services",
        MarketSegment.PUBLIC_IAAS_PAAS: "Public IaaS + PaaS",
    }
    PLAYER_LABELS: ClassVar[Dict[MarketPlayer, str]] = {
        MarketPlayer.AMAZON: "Amazon",
        MarketPlayer.MICROSOFT: "Microsoft",
        MarketPlayer.GOOGLE: "Google",
        MarketPlayer.BIG_THREE: "Big three",
        MarketPlayer.EUROPEAN_PROVIDERS: "European providers",
        MarketPlayer.SAP: "SAP",
        MarketPlayer.DEUTSCHE_TELEKOM: "Deutsche Telekom",
        MarketPlayer.NEOCLOUDS: "Neoclouds",
        MarketPlayer.OTHERS: "Others (computed)",
        MarketPlayer.ALIBABA: "Alibaba",
        MarketPlayer.IBM: "IBM",
        MarketPlayer.ORACLE: "Oracle",
        MarketPlayer.HUAWEI: "Huawei",
        MarketPlayer.TENCENT: "Tencent",
    }
    PLAYER_COLORS: ClassVar[Dict[MarketPlayer, str]] = {
        MarketPlayer.BIG_THREE: "#f0b429",
        MarketPlayer.EUROPEAN_PROVIDERS: "#2f6fde",
        MarketPlayer.SAP: "#0faaff",
        MarketPlayer.NEOCLOUDS: "#c792ea",
        MarketPlayer.OTHERS: "#6b7486",
    }
    BLOC_LABELS: ClassVar[Dict[GeoBloc, str]] = {
        GeoBloc.UNITED_STATES: "United States",
        GeoBloc.EUROPEAN_UNION: "European Union",
        GeoBloc.CHINA: "China",
        GeoBloc.RUSSIA: "Russia",
        GeoBloc.OTHER: "Other countries",
    }
    BLOC_COLORS: ClassVar[Dict[GeoBloc, str]] = {
        GeoBloc.UNITED_STATES: "#56B4E9",
        GeoBloc.EUROPEAN_UNION: "#F0E442",
        GeoBloc.CHINA: "#D55E00",
        GeoBloc.RUSSIA: "#CC79A7",
        GeoBloc.OTHER: "#999999",
    }
    LEVEL_COLORS: ClassVar[Dict[int, str]] = {
        logging.DEBUG: "#8b949e",
        logging.INFO: "#3fb950",
        logging.WARNING: "#d29922",
        logging.ERROR: "#f85149",
        logging.CRITICAL: "#ff7b72",
    }
    WARNING: ClassVar[str] = "#e3a008"
    DRIVER_POSITIVE: ClassVar[str] = "#3fb950"
    DRIVER_NEGATIVE: ClassVar[str] = "#f85149"
    DRIVER_FAINT: ClassVar[str] = "#4a5568"
    DRIVER_ROLE_COLORS: ClassVar[Dict[DriverRole, str]] = {
        DriverRole.TARGET: "#f0883e",
        DriverRole.CRITERION: "#4f8cff",
        DriverRole.CONTROL: "#a77bf3",
        DriverRole.SCOPE: "#3fb9a8",
        DriverRole.LAG: "#d29922",
    }
    WARNING_COLORS: ClassVar[Dict[WarningSeverity, str]] = {
        WarningSeverity.INFO: "#58a6ff",
        WarningSeverity.CAUTION: "#e3a008",
        WarningSeverity.BLOCKING: "#f85149",
    }
    POLICY_SHOCK: ClassVar[str] = "#e0726f"
    WARNING_SYMBOLS: ClassVar[Dict[WarningSeverity, str]] = {
        WarningSeverity.INFO: "i",
        WarningSeverity.CAUTION: "!",
        WarningSeverity.BLOCKING: "✕",
    }
    CAVEAT_LABELS: ClassVar[Dict[DateCaveat, str]] = {
        DateCaveat.PAGE_MODIFIED: (
            "it is when the provider's web page was last modified, maybe a change of the page only"
        ),
        DateCaveat.PAGE_PUBLISHED: "it is when the provider's web page was published, which may differ from the launch",
        DateCaveat.CATALOGUE_ENTRY: (
            "it is when the provider's catalogue entry was published or edited, which may differ from the launch or "
            "from a change of the product"
        ),
        DateCaveat.WEBSITE_RECORD: (
            "it is when the page was created in the provider's website, often by a website migration long after the "
            "launch"
        ),
        DateCaveat.ASSUMED_TIMEZONE: "it is read from the product identifier in China's time, it may be hours off",
        DateCaveat.YEAR_ONLY: "only the launch year is published, the day is unknown",
        DateCaveat.OLDEST_VERSION: "it is the release of the oldest version still listed, older ones may be gone",
        DateCaveat.FIRST_ANNOUNCEMENT: (
            "it is the first mention of the product in the provider's updates or release notes, the launch may be "
            "earlier"
        ),
        DateCaveat.FEED_START: "it is near the start of the provider's updates feed, the product may be older",
        DateCaveat.CURATED: "it is read by hand from the cited launch announcement",
    }

    def __init__(self) -> None:
        """Initialize the theme, without any flag drawn yet."""
        self.flags = FlagPainter()

    ############################
    # Publicly Exposed Methods #
    ############################

    def provider_color(self, provider: CloudProvider) -> QColor:
        """Get the accent colour of a cloud provider.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            QColor: The provider colour.
        """
        return QColor(self.PROVIDER_COLORS[provider])

    def provider_label(self, provider: CloudProvider) -> str:
        """Get the display name of a cloud provider.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            str: The provider display name, e.g. `Amazon Web Services`.
        """
        return self.PROVIDER_LABELS[provider]

    def country_label(self, country: Country) -> str:
        """Get the display name of a country.

        Args:
            country (Country): The country.

        Returns:
            str: The country display name, e.g. `United Kingdom`.
        """
        return self.COUNTRY_LABELS[country]

    def flag_icon(self, country: Country, height: int = 12) -> QIcon:
        """Get the flag icon of a country.

        Args:
            country (Country): The country.
            height (int): The flag height, in pixels.

        Returns:
            QIcon: The flag icon.
        """
        return self.flags.icon(country, height)

    def flag_pixmap(self, country: Country, height: int = 12) -> QPixmap:
        """Get the flag of a country.

        Args:
            country (Country): The country.
            height (int): The flag height, in pixels.

        Returns:
            QPixmap: The flag.
        """
        return self.flags.pixmap(country, height)

    def level_color(self, level: int) -> str:
        """Get the colour of a log level, the closest lower standard level for custom levels.

        Args:
            level (int): The log level number.

        Returns:
            str: The level colour.
        """
        known = [known for known in sorted(self.LEVEL_COLORS) if known <= level]
        return self.LEVEL_COLORS[known[-1]] if known else self.LEVEL_COLORS[logging.DEBUG]

    def dot_icon(self, color: QColor, size: int = 14) -> QIcon:
        """Draw a coloured disc icon.

        Args:
            color (QColor): The disc colour.
            size (int): The icon size, in pixels.

        Returns:
            QIcon: The icon.
        """
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QIcon(pixmap)

    def category_label(self, category: SoftwareCategory) -> str:
        """Get the display name of a software category.

        Args:
            category (SoftwareCategory): The software category.

        Returns:
            str: The category display name, e.g. `Developer tool`.
        """
        return self.CATEGORY_LABELS[category]

    def audience_label(self, audience: SoftwareAudience) -> str:
        """Get the display name of a software audience.

        Args:
            audience (SoftwareAudience): The software audience.

        Returns:
            str: The audience display name, e.g. `Both`.
        """
        return self.AUDIENCE_LABELS[audience]

    def audience_color(self, audience: SoftwareAudience) -> QColor:
        """Get the colour of a software audience.

        Args:
            audience (SoftwareAudience): The software audience.

        Returns:
            QColor: The audience colour.
        """
        return QColor(self.AUDIENCE_COLORS[audience])

    def company_color(self, company: Company) -> QColor:
        """Get the colour of a company of the computing chronology.

        Args:
            company (Company): The company.

        Returns:
            QColor: The colour of its cloud provider when it runs one (as everywhere else), else its own colour.
        """
        return QColor(self.PROVIDER_COLORS[company.provider] if company.provider else company.color)

    def driver_role_color(self, role: DriverRole) -> QColor:
        """Get the colour of a role of the driver analysis.

        Args:
            role (DriverRole): The role.

        Returns:
            QColor: Its colour.
        """
        return QColor(self.DRIVER_ROLE_COLORS[role])

    def warning_color(self, severity: WarningSeverity) -> QColor:
        """Get the colour of a severity of the driver warnings.

        Args:
            severity (WarningSeverity): The severity.

        Returns:
            QColor: Its colour.
        """
        return QColor(self.WARNING_COLORS[severity])

    def correspondence_fill(self, kind: CardinalityClass) -> QColor:
        """Get the fill of the service pills of a correspondence class.

        Args:
            kind (CardinalityClass): The class.

        Returns:
            QColor: The fill.
        """
        return QColor(self.CORRESPONDENCE_FILLS[kind])

    def correspondence_ink(self, kind: CardinalityClass) -> QColor:
        """Get the text colour on the pills of a correspondence class.

        Args:
            kind (CardinalityClass): The class.

        Returns:
            QColor: The text colour.
        """
        return QColor(self.CORRESPONDENCE_INKS[kind])

    def correspondence_edge(self, kind: CardinalityClass) -> QColor:
        """Get the connector colour of a correspondence class.

        Args:
            kind (CardinalityClass): The class.

        Returns:
            QColor: The connector colour.
        """
        return QColor(self.CORRESPONDENCE_EDGES[kind])

    def delivery_label(self, delivery: DeliveryMethod) -> str:
        """Get the display name of a delivery method.

        Args:
            delivery (DeliveryMethod): The delivery method.

        Returns:
            str: The delivery method display name, e.g. `SaaS`.
        """
        return self.DELIVERY_LABELS[delivery]

    def player_label(self, player: MarketPlayer) -> str:
        """Get the display name of a market player.

        Args:
            player (MarketPlayer): The market player.

        Returns:
            str: The player display name, e.g. `Amazon` or `Others (computed)`.
        """
        return self.PLAYER_LABELS[player]

    def player_color(self, player: MarketPlayer) -> QColor:
        """Get the colour of a market player: its provider colour when it is a crawled provider.

        Args:
            player (MarketPlayer): The market player.

        Returns:
            QColor: The player colour.
        """
        provider = player.provider
        return QColor(self.PROVIDER_COLORS[provider] if provider else self.PLAYER_COLORS[player])

    def bloc_label(self, bloc: GeoBloc) -> str:
        """Get the display name of a geopolitical bloc.

        Args:
            bloc (GeoBloc): The bloc.

        Returns:
            str: The bloc display name, e.g. `European Union`.
        """
        return self.BLOC_LABELS[bloc]

    def bloc_color(self, bloc: GeoBloc) -> QColor:
        """Get the colour of a geopolitical bloc.

        Args:
            bloc (GeoBloc): The bloc.

        Returns:
            QColor: The bloc colour.
        """
        return QColor(self.BLOC_COLORS[bloc])

    def date_label(self, value: Optional[datetime], caveat: Optional[DateCaveat] = None) -> str:
        """Get the short label of a date, in the local timezone.

        Args:
            value (Optional[datetime]): The date.
            caveat (Optional[DateCaveat]): Why it may be inaccurate, if it may be.

        Returns:
            str: The day (e.g. `2026-10-16`), the year only for a `YEAR_ONLY` date, empty when the date is unknown.
        """
        if value is None:
            return ""
        if caveat is DateCaveat.YEAR_ONLY:
            return f"{value.year}"
        return value.astimezone().strftime("%Y-%m-%d")

    def date_description(
        self, value: Optional[datetime], source: Optional[DateSource] = None, caveat: Optional[DateCaveat] = None
    ) -> str:
        """Describe a date, where it comes from and its caveat, in the local timezone.

        Args:
            value (Optional[datetime]): The date.
            source (Optional[DateSource]): Where it comes from, if known.
            caveat (Optional[DateCaveat]): Why it may be inaccurate, if it may be.

        Returns:
            str: The date and time with its origin (e.g. `2026-10-16 09:24, seen by a crawl`) and its caveat on a
                second line (starting with ⚠), `unknown` when the date is unknown.
        """
        if value is None:
            return "unknown"
        text = f"{value.year}" if caveat is DateCaveat.YEAR_ONLY else value.astimezone().strftime("%Y-%m-%d %H:%M")
        origins = {DateSource.WEBSITE: "published by the website", DateSource.CRAWL: "seen by a crawl"}
        text = f"{text}, {origins[source]}" if source else text
        return f"{text}\n\u26a0 Approximate: {self.CAVEAT_LABELS[caveat]}." if caveat else text

    def caveat_text(self, item: DatedItem) -> str:
        """Warn about the dates of a product or software which may be inaccurate.

        Args:
            item (DatedItem): The product or software.

        Returns:
            str: One warning per date with a caveat (starting with ⚠), empty when there is none.
        """
        caveats = (("added", item.added_at, item.added_caveat), ("updated", item.updated_at, item.updated_caveat))
        return "\n".join(
            f"\u26a0 The {label} date is approximate: {self.CAVEAT_LABELS[caveat]}."
            for label, value, caveat in caveats
            if value and caveat
        )

    def warning_icon(self, size: int = 14) -> QIcon:
        """Draw the warning icon: an exclamation mark in an amber triangle.

        Args:
            size (int): The icon size, in pixels.

        Returns:
            QIcon: The icon.
        """
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.WARNING))
        painter.drawPolygon(QPolygonF([QPointF(size / 2, 1), QPointF(size - 1, size - 1), QPointF(1, size - 1)]))
        painter.setPen(QColor(self.WINDOW))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(size - 5, 6))
        painter.setFont(font)
        painter.drawText(QRectF(0, 3, size, size - 3), Qt.AlignmentFlag.AlignCenter, "!")
        painter.end()
        return QIcon(pixmap)

    def history_text(self, item: DatedItem) -> str:
        """Describe when a product or software was added, updated and deleted, and where the dates come from.

        Args:
            item (DatedItem): The product or software.

        Returns:
            str: One line per date, the deletion only when the item was deleted.
        """
        lines = [
            f"Added: {self.date_description(item.added_at, item.added_from)}",
            f"Updated: {self.date_description(item.updated_at, item.updated_from)}",
        ]
        if item.deleted_at:
            lines.append(f"Deleted from the website: {self.date_description(item.deleted_at)}")
        return "\n".join(lines)

    def provider_icon(self, provider: CloudProvider) -> QIcon:
        """Get the coloured disc icon of a cloud provider.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            QIcon: The provider icon.
        """
        return self.dot_icon(self.provider_color(provider))

    def stylesheet(self) -> str:
        """Get the application stylesheet.

        Returns:
            str: The Qt stylesheet.
        """
        return f"""
            QWidget {{ background-color: {self.WINDOW}; color: {self.TEXT}; font-size: {self.UI_FONT_SIZE}px; }}
            {", ".join(self.CHART_WIDGETS)} {{ font-size: {self.CHART_FONT_SIZE}px; }}
            QToolBar {{ background-color: {self.SURFACE}; border: none; border-bottom: 1px solid {self.BORDER};
                spacing: 4px; padding: 4px; }}
            QToolButton {{ background-color: {self.SURFACE_ALT}; border: 1px solid {self.BORDER}; border-radius: 6px;
                padding: 4px 10px; }}
            QToolButton:hover {{ border-color: {self.ACCENT}; }}
            QToolButton:disabled {{ color: {self.TEXT_MUTED}; background-color: {self.SURFACE}; }}
            QListWidget, QTableView, QPlainTextEdit, QTextEdit {{ background-color: {self.SURFACE};
                border: 1px solid {self.BORDER}; border-radius: 8px; }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 6px; margin: 1px 4px; }}
            QListWidget::item:selected {{ background-color: {self.SURFACE_ALT}; color: {self.TEXT};
                border-left: 3px solid {self.ACCENT}; }}
            QTableView::item:selected {{ background-color: #263247; color: {self.TEXT}; }}
            QTableView {{ gridline-color: {self.BORDER}; alternate-background-color: #1c2230; }}
            QHeaderView::section {{ background-color: {self.SURFACE_ALT}; color: {self.TEXT_MUTED}; border: none;
                border-bottom: 1px solid {self.BORDER}; padding: 4px 6px; font-weight: 600; }}
            QLineEdit, QComboBox {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 6px; padding: 4px 8px; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {self.ACCENT}; }}
            QPushButton {{ background-color: {self.SURFACE_ALT}; border: 1px solid {self.BORDER}; border-radius: 6px;
                padding: 4px 12px; }}
            QPushButton:hover {{ border-color: {self.ACCENT}; }}
            QFrame#card, QFrame#details {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 10px; }}
            QFrame#card QLabel, QFrame#details QLabel {{ background: transparent; }}
            QLabel#muted {{ color: {self.TEXT_MUTED}; background: transparent; }}
            QLabel#warning {{ color: {self.WARNING}; background: transparent; }}
            QToolTip {{ background-color: {self.SURFACE_ALT}; color: {self.TEXT}; border: 1px solid {self.BORDER};
                border-radius: 6px; padding: 6px; }}
            QFrame#columnGuide {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 8px; }}
            QLabel#guideTitle {{ font-weight: bold; background: transparent; }}
            QLabel#guideEntry {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
                padding: 3px 6px; }}
            QLabel#guideEntry:hover {{ background-color: {self.SURFACE_ALT}; border-color: {self.BORDER}; }}
            QLabel#guideEntry[active="true"] {{ background-color: {self.SURFACE_ALT}; border-color: {self.ACCENT}; }}
            QLabel#title {{ font-size: 16px; font-weight: 700; background: transparent; }}
            QLabel#value {{ font-size: 20px; font-weight: 700; background: transparent; }}
            QDockWidget::title {{ background-color: {self.SURFACE_ALT}; padding: 4px; }}
            QStatusBar {{ background-color: {self.SURFACE}; border-top: 1px solid {self.BORDER}; }}
            QProgressBar {{ background-color: {self.SURFACE_ALT}; border: none; border-radius: 4px; max-height: 8px; }}
            QProgressBar::chunk {{ background-color: {self.ACCENT}; border-radius: 4px; }}
            QSplitter::handle {{ background-color: {self.BORDER}; }}
            QFrame#chartCard {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 10px; }}
            QFrame#chartCard QLabel, QFrame#chartCard QCheckBox {{ background: transparent; }}
            QToolButton#sectionToggle {{ background: transparent; border: none; padding: 2px 4px; font-size: 13px;
                font-weight: 600; }}
            QToolButton#sectionToggle:hover, QToolButton#sectionToggle:focus {{ color: {self.ACCENT}; }}
            QToolButton#segment {{ padding: 3px 9px; border-radius: 0px; }}
            QToolButton#segment:checked {{ background-color: #263247; border-color: {self.ACCENT}; }}
            QToolButton#chartTool {{ padding: 3px 7px; }}
            QToolButton#chartTool::menu-indicator {{ image: none; }}
            QLabel#chartSubtitle {{ color: {self.TEXT_MUTED}; font-size: 11px; background: transparent; }}
            QLabel#footnote {{ color: {self.TEXT_MUTED}; font-size: 10px; background: transparent; }}
            QMenu {{ background-color: {self.SURFACE_ALT}; border: 1px solid {self.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 22px 4px 18px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: #263247; }}
            QMenu::item:disabled {{ color: {self.TEXT_MUTED}; }}
            QMenu::section {{ color: {self.TEXT_MUTED}; padding: 6px 8px 2px 8px; font-weight: 600; }}
        """

    def apply(self, app: QApplication) -> None:
        """Apply the theme to the application.

        Args:
            app (QApplication): The application.
        """
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.WINDOW))
        palette.setColor(QPalette.ColorRole.Base, QColor(self.SURFACE))
        palette.setColor(QPalette.ColorRole.Text, QColor(self.TEXT))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self.TEXT))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(self.ACCENT))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(self.SURFACE_ALT))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(self.TEXT))
        app.setPalette(palette)
        app.setStyleSheet(self.stylesheet())
