from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import Final

CONF_DIR: Final[Path] = Path(__file__).parent
LOGGER_CONFIG_PATH: Final[Path] = CONF_DIR / "logger.yaml"
CLASSIFICATION_RULES_PATH: Final[Path] = CONF_DIR / "classification.yaml"
TAXONOMY_DIR: Final[Path] = CONF_DIR / "taxonomy"
TAXONOMY_SEED_PATH: Final[Path] = TAXONOMY_DIR / "taxonomy.yaml"
LABEL_SEED_PATH: Final[Path] = TAXONOMY_DIR / "label-seed.yaml"
TAXONOMY_PROMPTS_PATH: Final[Path] = TAXONOMY_DIR / "prompts.yaml"
LLM_CONFIG_PATH: Final[Path] = CONF_DIR / "llm.yaml"
SETTINGS_PATH: Final[Path] = CONF_DIR / "settings.yaml"
HELP_PATH: Final[Path] = CONF_DIR / "help.yaml"
CURATED_DIR: Final[Path] = CONF_DIR.parents[1] / "data" / "curated"
METRICS_DIR: Final[Path] = CONF_DIR / "metrics"
METRICS_CATALOG_PATH: Final[Path] = METRICS_DIR / "metrics.yaml"
MANUAL_METRICS_PATH: Final[Path] = METRICS_DIR / "manual-metrics.yaml"
METRIC_COLLECTORS_PATH: Final[Path] = METRICS_DIR / "collectors.yaml"
CHRONOLOGY_DOC_PATH: Final[Path] = CONF_DIR.parents[1] / "docs" / "analysis" / "leaders-chronology.md"
MARKETS_DOC_PATH: Final[Path] = CONF_DIR.parents[1] / "docs" / "analysis" / "market-shares-and-stocks.md"
COMPANIES_DOC_PATH: Final[Path] = CONF_DIR.parents[1] / "docs" / "analysis" / "company-financials-and-rd.md"
ANALYSIS_DIR: Final[Path] = CONF_DIR / "analysis"
COMPOUNDING_PATH: Final[Path] = ANALYSIS_DIR / "compounding.yaml"
PRICE_COVERAGE_DIR: Final[Path] = CONF_DIR / "prices" / "coverage"
COMPOUNDING_DOC_PATH: Final[Path] = (
    CONF_DIR.parents[1] / "docs" / "analysis" / "service-capability-compounding-results.md"
)
