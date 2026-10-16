from __future__ import annotations

# Standard Library Imports.
import logging
from datetime import datetime
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication

# First Party Imports.
from gui.flags.flag_painter import FlagPainter
from models.cloud.dated_item import DatedItem
from models.cloud.enums import (
    CloudProvider,
    Country,
    DateSource,
    DeliveryMethod,
    MarketPlayer,
    MarketRegion,
    MarketSegment,
    SoftwareCategory,
    SoftwareType,
)


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
        TYPE_LABELS (ClassVar[Dict[SoftwareType, str]]): The display names of the software types which are not the
            capitalized enum value, e.g. `CRM`.
        DELIVERY_LABELS (ClassVar[Dict[DeliveryMethod, str]]): The display name of each delivery method.
        REGION_LABELS (ClassVar[Dict[MarketRegion, str]]): The display name of each market region.
        SEGMENT_LABELS (ClassVar[Dict[MarketSegment, str]]): The display name of each market segment.
        PLAYER_LABELS (ClassVar[Dict[MarketPlayer, str]]): The display name of each market player.
        PLAYER_COLORS (ClassVar[Dict[MarketPlayer, str]]): The colour of the market players which are not crawled
            providers (the others take their provider colour).
        LEVEL_COLORS (ClassVar[Dict[int, str]]): The colour of each log level.
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
    }
    CATEGORY_LABELS: ClassVar[Dict[SoftwareCategory, str]] = {
        SoftwareCategory.DEVELOPER_TOOL: "Developer tool",
        SoftwareCategory.END_USER_SOFTWARE: "End-user software",
    }
    CATEGORY_COLORS: ClassVar[Dict[SoftwareCategory, str]] = {
        SoftwareCategory.DEVELOPER_TOOL: "#4f8cff",
        SoftwareCategory.END_USER_SOFTWARE: "#3fb950",
    }
    TYPE_LABELS: ClassVar[Dict[SoftwareType, str]] = {
        SoftwareType.ATS: "ATS",
        SoftwareType.CRM: "CRM",
        SoftwareType.ERP: "ERP",
        SoftwareType.HRIS: "HRIS",
        SoftwareType.ECOMMERCE: "E-commerce",
        SoftwareType.CMS: "CMS",
        SoftwareType.E_LEARNING: "E-learning",
        SoftwareType.ITSM: "ITSM",
        SoftwareType.AI_ML: "AI / ML",
        SoftwareType.DEVOPS: "DevOps",
        SoftwareType.API_MANAGEMENT: "API management",
        SoftwareType.IOT: "IoT",
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
    }
    PLAYER_COLORS: ClassVar[Dict[MarketPlayer, str]] = {
        MarketPlayer.BIG_THREE: "#f0b429",
        MarketPlayer.EUROPEAN_PROVIDERS: "#2f6fde",
        MarketPlayer.SAP: "#0faaff",
        MarketPlayer.NEOCLOUDS: "#c792ea",
        MarketPlayer.OTHERS: "#6b7486",
    }
    LEVEL_COLORS: ClassVar[Dict[int, str]] = {
        logging.DEBUG: "#8b949e",
        logging.INFO: "#3fb950",
        logging.WARNING: "#d29922",
        logging.ERROR: "#f85149",
        logging.CRITICAL: "#ff7b72",
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

    def type_label(self, kind: SoftwareType) -> str:
        """Get the display name of a software type.

        Args:
            kind (SoftwareType): The software type.

        Returns:
            str: The type display name, e.g. `CRM` or `Project management`.
        """
        return self.TYPE_LABELS.get(kind, kind.value.replace("-", " ").capitalize())

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

    def date_label(self, value: Optional[datetime]) -> str:
        """Get the short label of a date, in the local timezone.

        Args:
            value (Optional[datetime]): The date.

        Returns:
            str: The day (e.g. `2026-10-16`), empty when the date is unknown.
        """
        return value.astimezone().strftime("%Y-%m-%d") if value else ""

    def date_description(self, value: Optional[datetime], source: Optional[DateSource] = None) -> str:
        """Describe a date and where it comes from, in the local timezone.

        Args:
            value (Optional[datetime]): The date.
            source (Optional[DateSource]): Where it comes from, if known.

        Returns:
            str: The date and time with its origin (e.g. `2026-10-16 09:24, seen by a crawl`), `unknown` when the date
                is unknown.
        """
        if value is None:
            return "unknown"
        text = value.astimezone().strftime("%Y-%m-%d %H:%M")
        origins = {DateSource.WEBSITE: "published by the website", DateSource.CRAWL: "seen by a crawl"}
        return f"{text}, {origins[source]}" if source else text

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
            QWidget {{ background-color: {self.WINDOW}; color: {self.TEXT}; font-size: 13px; }}
            QToolBar {{ background-color: {self.SURFACE}; border: none; border-bottom: 1px solid {self.BORDER};
                spacing: 6px; padding: 6px; }}
            QToolButton {{ background-color: {self.SURFACE_ALT}; border: 1px solid {self.BORDER}; border-radius: 6px;
                padding: 6px 12px; }}
            QToolButton:hover {{ border-color: {self.ACCENT}; }}
            QToolButton:disabled {{ color: {self.TEXT_MUTED}; background-color: {self.SURFACE}; }}
            QListWidget, QTableView, QPlainTextEdit, QTextEdit {{ background-color: {self.SURFACE};
                border: 1px solid {self.BORDER}; border-radius: 8px; }}
            QListWidget::item {{ padding: 10px 8px; border-radius: 6px; margin: 2px 4px; }}
            QListWidget::item:selected {{ background-color: {self.SURFACE_ALT}; color: {self.TEXT};
                border-left: 3px solid {self.ACCENT}; }}
            QTableView::item:selected {{ background-color: #263247; color: {self.TEXT}; }}
            QTableView {{ gridline-color: {self.BORDER}; alternate-background-color: #1c2230; }}
            QHeaderView::section {{ background-color: {self.SURFACE_ALT}; color: {self.TEXT_MUTED}; border: none;
                border-bottom: 1px solid {self.BORDER}; padding: 6px; font-weight: 600; }}
            QLineEdit, QComboBox {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 6px; padding: 6px 10px; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {self.ACCENT}; }}
            QPushButton {{ background-color: {self.SURFACE_ALT}; border: 1px solid {self.BORDER}; border-radius: 6px;
                padding: 6px 14px; }}
            QPushButton:hover {{ border-color: {self.ACCENT}; }}
            QFrame#card, QFrame#details {{ background-color: {self.SURFACE}; border: 1px solid {self.BORDER};
                border-radius: 10px; }}
            QFrame#card QLabel, QFrame#details QLabel {{ background: transparent; }}
            QLabel#muted {{ color: {self.TEXT_MUTED}; background: transparent; }}
            QLabel#title {{ font-size: 18px; font-weight: 700; background: transparent; }}
            QLabel#value {{ font-size: 24px; font-weight: 700; background: transparent; }}
            QDockWidget::title {{ background-color: {self.SURFACE_ALT}; padding: 6px; }}
            QStatusBar {{ background-color: {self.SURFACE}; border-top: 1px solid {self.BORDER}; }}
            QProgressBar {{ background-color: {self.SURFACE_ALT}; border: none; border-radius: 4px; max-height: 8px; }}
            QProgressBar::chunk {{ background-color: {self.ACCENT}; border-radius: 4px; }}
            QSplitter::handle {{ background-color: {self.BORDER}; }}
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
        app.setPalette(palette)
        app.setStyleSheet(self.stylesheet())
