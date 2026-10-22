from __future__ import annotations

# Standard Library Imports.
import json
import re
from logging import Logger, getLogger
from typing import ClassVar, Dict, Iterator, List, Optional, Sequence

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.exception import CatalogueFormatError


class NextFlightData:
    """Reader of the React Server Components data (the Next.js "flight" data) embedded in a page.

    Attributes:
        PUSH (ClassVar[str]): The call of the scripts pushing a chunk of the flight data.
        DATA_CHUNK (ClassVar[int]): The first element of the pushed arrays holding a chunk of the flight data.
        JSON_ROW (ClassVar[re.Pattern[str]]): The start of a flight data row holding a JSON object or array.
        crawler (str): The name of the crawler reading the pages, for the logs and the errors.
        logger (Logger): The reader logger, the crawler one.

    Notes:
        The pages rendered by the Next.js App Router have no `__NEXT_DATA__` script: their data is streamed by
        `self.__next_f.push([1, "<chunk>"])` scripts. The chunks, joined in order (a row may be split between two
        chunks), are rows of the form `<id>:<payload>`. Each JSON row (a payload starting with `[` or `{`) is decoded
        from its start, the other rows (module references, text rows) are skipped. A value repeated in the data may
        be replaced by a reference to its first occurrence (a `$...` text): the readers type-check every value they
        use. Read by the Cloud.ru and VK Cloud crawlers.
    """

    PUSH: ClassVar[str] = "self.__next_f.push("
    DATA_CHUNK: ClassVar[int] = 1
    JSON_ROW: ClassVar[re.Pattern[str]] = re.compile(r"^[0-9a-f]+:(?=[\[{])", re.MULTILINE)

    def __init__(self, crawler: str, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            crawler (str): The name of the crawler reading the pages.
            logger (Optional[Logger]): The crawler logger, a module logger by default.
        """
        self.crawler = crawler
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Flight data reader of %s ready.", crawler)

    ############################
    # Internal Helpers Methods #
    ############################

    def _chunks(self, response: Response) -> List[str]:
        """Read the chunks of flight data pushed by the scripts of a page, in order.

        Args:
            response (Response): The page.

        Returns:
            List[str]: The chunks, empty when the page pushes none (the unreadable scripts are skipped).
        """
        chunks: List[str] = []
        for script in response.css("script::text").getall():
            text = str(script)
            start = text.find(self.PUSH)
            if start < 0:
                continue
            try:
                pushed: JsonValue = json.loads(text[start + len(self.PUSH) : text.rfind(")")])
            except json.JSONDecodeError as e:
                self.logger.warning(
                    "Skipping an unreadable %s flight data script of %s: %s", self.crawler, response.url, e
                )
                continue
            if isinstance(pushed, list) and len(pushed) > 1 and pushed[0] == self.DATA_CHUNK:  # noqa: E501
                chunk = pushed[1]
                chunks.extend([chunk] if isinstance(chunk, str) else [])
        self.logger.debug("%d %s flight data chunks in %s.", len(chunks), self.crawler, response.url)  # noqa: E501
        return chunks

    def _walk(self, value: JsonValue) -> Iterator[Dict[str, JsonValue]]:
        """Walk every JSON object of a JSON document, depth first.

        Args:
            value (JsonValue): The JSON document.

        Yields:
            Dict[str, JsonValue]: Each object, parents before their children.
        """
        children: List[JsonValue] = []
        if isinstance(value, dict):
            yield value
            children = list(value.values())
        elif isinstance(value, list):
            children = value
        for child in children:
            yield from self._walk(child)

    def _decode(self, text: str, url: str) -> List[JsonValue]:
        """Decode the JSON rows of the joined flight data.

        Args:
            text (str): The chunks, joined in order.
            url (str): The page, for the logs.

        Returns:
            List[JsonValue]: The JSON payload of each JSON row, in order.
        """
        decoder = json.JSONDecoder()
        documents: List[JsonValue] = []
        for match in self.JSON_ROW.finditer(text):
            try:
                document, _ = decoder.raw_decode(text, match.end())
            except json.JSONDecodeError:
                self.logger.debug("Skipping an unreadable %s flight data row of %s.", self.crawler, url)
                continue
            documents.append(document)
        self.logger.debug("%d JSON rows in the %s flight data of %s.", len(documents), self.crawler, url)  # noqa: E501
        return documents

    ############################
    # Publicly Exposed Methods #
    ############################

    def rows(self, response: Response) -> List[JsonValue]:
        """Read the JSON rows of the flight data of a page, none for a page without flight data.

        Args:
            response (Response): The page.

        Returns:
            List[JsonValue]: The JSON payload of each JSON row, in order, empty without flight data.
        """
        return self._decode("".join(self._chunks(response)), str(response.url))

    def documents(self, response: Response) -> List[JsonValue]:
        """Read the JSON rows of the flight data of a page which must hold some.

        Args:
            response (Response): The page.

        Returns:
            List[JsonValue]: The JSON payload of each JSON row, in order.

        Raises:
            CatalogueFormatError: If the page pushes no flight data.
        """
        chunks = self._chunks(response)
        if not chunks:
            self.logger.error("The %s page %s holds no flight data.", self.crawler, response.url)  # noqa: E501
            raise CatalogueFormatError(self.crawler, response.url, "the page holds no Next.js flight data")
        return self._decode("".join(chunks), str(response.url))

    def objects(self, documents: Sequence[JsonValue]) -> Iterator[Dict[str, JsonValue]]:  # noqa: E501
        """Walk every JSON object of the flight data.

        Args:
            documents (Sequence[JsonValue]): The JSON rows of the flight data.

        Yields:
            Dict[str, JsonValue]: Each object, row by row, parents before their children.
        """
        for document in documents:
            yield from self._walk(document)

    def find(self, documents: Sequence[JsonValue], *lists: str) -> Optional[Dict[str, JsonValue]]:  # noqa: E501
        """Find the first object of the flight data holding some lists.

        Args:
            documents (Sequence[JsonValue]): The JSON rows of the flight data.
            *lists (str): The keys whose values must be JSON arrays, e.g. `products` and `categories`.

        Returns:
            Optional[Dict[str, JsonValue]]: The object, `None` when no object holds them all.
        """
        for value in self.objects(documents):
            if all(isinstance(value.get(key), list) for key in lists):
                self.logger.debug("Flight data object with the lists %s found.", ", ".join(lists))
                return value
        self.logger.debug("No flight data object with the lists %s.", ", ".join(lists))  # noqa: E501
        return None
