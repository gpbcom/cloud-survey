from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import Final

CONF_DIR: Final[Path] = Path(__file__).parent
LOGGER_CONFIG_PATH: Final[Path] = CONF_DIR / "logger.yaml"
CLASSIFICATION_RULES_PATH: Final[Path] = CONF_DIR / "classification.yaml"
