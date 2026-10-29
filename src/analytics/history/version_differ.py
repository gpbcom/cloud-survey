from __future__ import annotations

# Standard Library Imports.
import json
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from pydantic import JsonValue

# First Party Imports.
from models.storage.versions.item_version import ItemVersion
from models.storage.versions.version_change import VersionChange


class VersionDiffer:
    """Compare the stored versions of an item: what each crawl added, removed and changed.

    Attributes:
        ELLIPSIS (ClassVar[str]): The mark ending a truncated value.
        EMPTY (ClassVar[str]): The text of a missing value (a JSON `null`).
        logger (Logger): The differ logger.

    Notes:
        - Each version is compared with the previous one (the next older). The oldest version is the item first seen
          (`first`), with no field added, removed or changed.
        - The values are compared as canonical JSON text (sorted keys), so the lists and objects are compared whole.
        - The values are written as short texts: a text as it is, anything else as JSON, truncated to
          `VersionChange.TEXT_LIMIT` characters.
    """

    ELLIPSIS: ClassVar[str] = "…"
    EMPTY: ClassVar[str] = "(empty)"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the differ.

        Args:
            logger (Optional[Logger]): The differ logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _canonical(self, value: JsonValue) -> str:
        """Write a value as canonical JSON, to compare it.

        Args:
            value (JsonValue): The value.

        Returns:
            str: Its JSON text, the keys sorted.
        """
        return json.dumps(value, sort_keys=True, ensure_ascii=False)

    def _text(self, value: JsonValue) -> str:
        """Write a value as a short text, for display.

        Args:
            value (JsonValue): The value.

        Returns:
            str: The text itself, `EMPTY` for a missing value, else JSON, truncated with an ellipsis.
        """
        if value is None:
            return self.EMPTY
        text = " ".join(value.split()) if isinstance(value, str) else self._canonical(value)
        limit = VersionChange.TEXT_LIMIT
        return text if len(text) <= limit else text[: limit - len(self.ELLIPSIS)] + self.ELLIPSIS

    def _compare(
        self, older: Dict[str, JsonValue], newer: Dict[str, JsonValue]
    ) -> Tuple[List[str], List[str], List[Tuple[str, str, str]]]:
        """Compare two contents.

        Args:
            older (Dict[str, JsonValue]): The content of the previous version.
            newer (Dict[str, JsonValue]): The content of the version.

        Returns:
            Tuple[List[str], List[str], List[Tuple[str, str, str]]]: The fields added, removed and changed (with the
                value before and after), each sorted by field name.
        """
        added = sorted(set(newer) - set(older))
        removed = sorted(set(older) - set(newer))
        changed = [
            (field, self._text(older[field]), self._text(newer[field]))
            for field in sorted(set(older) & set(newer))
            if self._canonical(older[field]) != self._canonical(newer[field])
        ]
        return added, removed, changed

    ############################
    # Publicly Exposed Methods #
    ############################

    def changes(self, versions: Sequence[ItemVersion]) -> List[VersionChange]:
        """Get what each version changed against the previous one.

        Args:
            versions (Sequence[ItemVersion]): The versions of an item, in any order.

        Returns:
            List[VersionChange]: One change per version, the newest first, the oldest marked first seen.
        """
        ordered = sorted(versions, key=lambda version: (version.recorded_at, version.crawl_id))
        changes: List[VersionChange] = []
        previous: Optional[ItemVersion] = None
        for version in ordered:
            if previous is None:
                changes.append(VersionChange(crawl_id=version.crawl_id, recorded_at=version.recorded_at, first=True))
            else:
                added, removed, changed = self._compare(previous.content, version.content)
                changes.append(
                    VersionChange(
                        crawl_id=version.crawl_id,
                        recorded_at=version.recorded_at,
                        added=added,
                        removed=removed,
                        changed=changed,
                    )
                )
            previous = version
        changes.reverse()
        self.logger.debug("%d versions compared.", len(changes))
        return changes
