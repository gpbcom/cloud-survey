from __future__ import annotations

from typing import Union

# Third Party Imports.
from pydantic import JsonValue

# First Party Imports.
from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.enums import FormatterKind


class FormatterDiscriminator:
    """Tell which formatter configuration model applies to a formatter configuration.

    Attributes:
        FACTORY_KEYS (frozenset[str]): The keys only found in factory based configurations.

    Notes:
        `()` factory based configurations are coloured, `class` based ones are standard.
    """

    FACTORY_KEYS: frozenset[str] = frozenset({"()", "factory"})

    @staticmethod
    def get_kind(value: Union[JsonValue, BaseFormatterConfig]) -> FormatterKind:
        """Get the kind of a formatter configuration.

        Args:
            value (Union[JsonValue, BaseFormatterConfig]): The raw formatter configuration,
                or an already built one.

        Returns:
            FormatterKind: The formatter configuration kind.
        """
        if isinstance(value, dict):
            is_factory = not FormatterDiscriminator.FACTORY_KEYS.isdisjoint(value)
        else:
            is_factory = getattr(value, "factory", None) is not None
        return FormatterKind.COLOURED if is_factory else FormatterKind.STANDARD
