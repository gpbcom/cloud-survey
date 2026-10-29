from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.drivers.enums import DriverColumn, DriverRole, DriverWarningKind, MetricValueColumn
from models.drivers.help.choice_help import ChoiceHelp
from models.drivers.help.column_help import ColumnHelp
from models.drivers.help.role_help import RoleHelp
from models.drivers.help.value_column_help import ValueColumnHelp
from models.drivers.help.warning_help import WarningHelp


class DriverHelp(BaseModel):
    """The explanations of the driver analysis: the role of each parameter, the meaning of each warning and column.

    Attributes:
        roles (List[RoleHelp]): The roles, in the order of the legend.
        warnings (List[WarningHelp]): The warnings.
        columns (List[ColumnHelp]): The columns of the table, in the order of the guide.
        choices (List[ChoiceHelp]): The scales and the scopes, explained in the tooltips of the criteria and of the
            scope list.
        value_columns (List[ValueColumnHelp]): The columns of the table of the stored provider metrics, in their
            order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: List[RoleHelp] = Field(default_factory=list, description="The roles, in the order of the legend.")
    warnings: List[WarningHelp] = Field(default_factory=list, description="The warnings.")
    columns: List[ColumnHelp] = Field(default_factory=list, description="The columns of the table.")
    choices: List[ChoiceHelp] = Field(default_factory=list, description="The scales and the scopes.")
    value_columns: List[ValueColumnHelp] = Field(
        default_factory=list, description="The columns of the table of the stored provider metrics."
    )

    ############################
    # Publicly Exposed Methods #
    ############################

    def role(self, role: DriverRole) -> Optional[RoleHelp]:
        """Get the explanation of a role.

        Args:
            role (DriverRole): The role.

        Returns:
            Optional[RoleHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.roles if entry.role is role), None)

    def column(self, column: DriverColumn) -> Optional[ColumnHelp]:
        """Get the explanation of a column of the table.

        Args:
            column (DriverColumn): The column.

        Returns:
            Optional[ColumnHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.columns if entry.column is column), None)

    def warning(self, kind: DriverWarningKind) -> Optional[WarningHelp]:
        """Get the explanation of a warning.

        Args:
            kind (DriverWarningKind): The warning.

        Returns:
            Optional[WarningHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.warnings if entry.kind is kind), None)

    def choice(self, choice: str) -> Optional[ChoiceHelp]:
        """Get the explanation of a scale or a scope.

        Args:
            choice (str): The scale or scope value.

        Returns:
            Optional[ChoiceHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.choices if entry.choice == choice), None)

    def value_column(self, column: MetricValueColumn) -> Optional[ValueColumnHelp]:
        """Get the explanation of a column of the table of the stored provider metrics.

        Args:
            column (MetricValueColumn): The column.

        Returns:
            Optional[ValueColumnHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.value_columns if entry.column is column), None)
