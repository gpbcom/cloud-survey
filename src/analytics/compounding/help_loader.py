from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from analytics.compounding.exception import CompoundingFileError
from conf import HELP_PATH
from models.compounding.help.compounding_help import CompoundingHelp


class CompoundingHelpLoader:
    """Load the explanations of the Service compounding section.

    Attributes:
        BLOCK (ClassVar[str]): The block of `conf/help.yaml` holding the explanations.
        logger (Logger): The loader logger.

    Notes:
        The explanations are the `compounding` block of `conf/help.yaml`.
    """

    BLOCK: ClassVar[str] = "compounding"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self, path: Path = HELP_PATH) -> CompoundingHelp:
        """Read and validate the explanations.

        Args:
            path (Path): The help file, whose block holds the explanations.

        Returns:
            CompoundingHelp: The explanations.

        Raises:
            CompoundingFileError: If the file cannot be read, is not valid YAML or is invalid.
        """
        try:
            with path.open(encoding="utf-8") as file:
                content = yaml.safe_load(file) or {}
                block = content.get(self.BLOCK) if isinstance(content, dict) else None
                if not isinstance(block, dict):
                    self.logger.error("The compounding help %s have no %s block.", path, self.BLOCK)
                    raise CompoundingFileError(str(path), f"the file has no `{self.BLOCK}` block.")
                help_texts = CompoundingHelp.model_validate(block)
        except OSError as e:
            self.logger.error("The compounding help %s cannot be read: %s", path, e.strerror)
            raise CompoundingFileError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The compounding help %s is not valid YAML.", path)
            raise CompoundingFileError(str(path), f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The compounding help %s is invalid (%d errors).", path, e.error_count())
            raise CompoundingFileError(str(path), f"the content is invalid.\n{e}") from e
        self.logger.debug(
            "Compounding help loaded: %d columns, %d cards.", len(help_texts.columns), len(help_texts.cards)
        )
        return help_texts
