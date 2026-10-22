from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from analytics.drivers.exception import DriverHelpFileError
from conf import DRIVERS_HELP_PATH
from models.drivers.enums import DriverColumn, DriverRole, DriverWarningKind
from models.drivers.help.driver_help import DriverHelp


class DriverHelpLoader:
    """Load the explanations of the driver analysis: the roles and the warnings (`conf/metrics/drivers-help.yaml`).

    Attributes:
        logger (Logger): The loader logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self, path: Path = DRIVERS_HELP_PATH) -> DriverHelp:
        """Read and validate the explanations.

        Args:
            path (Path): The explanations file.

        Returns:
            DriverHelp: The explanation of each role and each warning.

        Raises:
            DriverHelpFileError: If the file cannot be read, is not valid YAML or holds invalid explanations.
        """
        try:
            with path.open(encoding="utf-8") as file:
                help_ = DriverHelp.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The driver explanations %s cannot be read: %s", path, e.strerror)
            raise DriverHelpFileError(path, f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The driver explanations %s are not valid YAML.", path)
            raise DriverHelpFileError(path, f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The driver explanations %s are invalid (%d errors).", path, e.error_count())
            raise DriverHelpFileError(path, f"the content is invalid.\n{e}") from e
        missing = [role.value for role in DriverRole if help_.role(role) is None]
        missing += [kind.value for kind in DriverWarningKind if help_.warning(kind) is None]
        missing += [column.value for column in DriverColumn if help_.column(column) is None]
        if missing:
            self.logger.warning("The driver explanations %s miss: %s.", path, ", ".join(missing))
        self.logger.debug("Driver explanations loaded: %d roles, %d warnings.", len(help_.roles), len(help_.warnings))
        return help_
