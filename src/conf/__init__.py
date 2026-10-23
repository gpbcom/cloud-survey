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
METRICS_DIR: Final[Path] = CONF_DIR / "metrics"
METRICS_CATALOG_PATH: Final[Path] = METRICS_DIR / "metrics.yaml"
MANUAL_METRICS_PATH: Final[Path] = METRICS_DIR / "manual-metrics.yaml"
METRIC_COLLECTORS_PATH: Final[Path] = METRICS_DIR / "collectors.yaml"
DRIVERS_HELP_PATH: Final[Path] = METRICS_DIR / "drivers-help.yaml"
HISTORY_DIR: Final[Path] = CONF_DIR / "history"
CHRONOLOGY_PATH: Final[Path] = HISTORY_DIR / "chronology.yaml"
CHRONOLOGY_DOC_PATH: Final[Path] = CONF_DIR.parents[1] / "docs" / "analysis" / "leaders-chronology.md"
MARKETS_PATH: Final[Path] = HISTORY_DIR / "markets.yaml"
MARKETS_DOC_PATH: Final[Path] = CONF_DIR.parents[1] / "docs" / "analysis" / "market-shares-and-stocks.md"
