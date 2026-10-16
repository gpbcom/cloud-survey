from __future__ import annotations

# Standard Library Imports.
from typing import Annotated, Union

# Third Party Imports.
from pydantic import Discriminator, Tag

# First Party Imports.
from models.configuration.logging.enums import FormatterKind
from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig
from models.configuration.logging.formatters.standard_formatter_config import StandardFormatterConfig
from models.configuration.logging.utils.formatter_discriminator import FormatterDiscriminator

# Every supported formatter configuration: `()` factory based ones are coloured, `class` based ones are standard.
FormatterConfig = Annotated[
    Union[
        Annotated[StandardFormatterConfig, Tag(FormatterKind.STANDARD)],
        Annotated[ColouredFormatterConfig, Tag(FormatterKind.COLOURED)],
    ],
    Discriminator(FormatterDiscriminator.get_kind),
]
