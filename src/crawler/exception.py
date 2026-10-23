from __future__ import annotations


class CrawlerError(Exception):
    """Base class for every error raised by the crawlers.

    Attributes:
        message (str): Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class UnknownCrawlerTargetError(CrawlerError, ValueError):
    """Raised when no crawler is available for the requested target.

    Attributes:
        target (str): The requested target.
    """

    def __init__(self, target: str) -> None:
        """Initialize the error.

        Args:
            target (str): The requested target.
        """
        self.target = target
        super().__init__(f"Failed to identify suitable crawler for target: {target!r}.")


class ParseNotImplementedError(CrawlerError, NotImplementedError):
    """Raised when a crawler does not implement the `parse` method.

    Attributes:
        crawler (str): The crawler class name.
    """

    def __init__(self, crawler: str) -> None:
        """Initialize the error.

        Args:
            crawler (str): The crawler class name.
        """
        self.crawler = crawler
        super().__init__(f"{crawler}: the `parse` methods will be implemented in children classes.")


class CatalogueFormatError(CrawlerError):
    """Raised when a catalogue page no longer has the structure a crawler expects.

    Attributes:
        crawler (str): The crawler name.
        url (str): The catalogue page URL.
        reason (str): Human-readable explanation of what is unexpected.
    """

    def __init__(self, crawler: str, url: str, reason: str) -> None:
        """Initialize the error.

        Args:
            crawler (str): The crawler name.
            url (str): The catalogue page URL.
            reason (str): Human-readable explanation of what is unexpected.
        """
        self.crawler = crawler
        self.url = url
        self.reason = reason
        super().__init__(f"{crawler}: unexpected catalogue format at {url}: {reason}.")


class EmptyCatalogueError(CrawlerError):
    """Raised when a catalogue page yields no product at all.

    Attributes:
        crawler (str): The crawler name.
        url (str): The catalogue page URL.
    """

    def __init__(self, crawler: str, url: str) -> None:
        """Initialize the error.

        Args:
            crawler (str): The crawler name.
            url (str): The catalogue page URL.
        """
        self.crawler = crawler
        self.url = url
        super().__init__(f"{crawler}: no product found at {url}.")


class EmptyCrawlError(CrawlerError):
    """Raised when a whole crawl produced no product: the previous catalogue file is kept.

    Attributes:
        provider (str): The crawled cloud provider.
    """

    def __init__(self, provider: str) -> None:
        """Initialize the error.

        Args:
            provider (str): The crawled cloud provider.
        """
        self.provider = provider
        super().__init__(f"The {provider} crawl produced no product: its catalogue file is left unchanged.")


class NoMarketplaceError(CrawlerError, ValueError):
    """Raised when a cloud provider has no marketplace to crawl.

    Attributes:
        provider (str): The cloud provider.
    """

    def __init__(self, provider: str) -> None:
        """Initialize the error.

        Args:
            provider (str): The cloud provider.
        """
        self.provider = provider
        super().__init__(f"The {provider} cloud provider has no marketplace to crawl.")


class CollectorCatalogError(CrawlerError):
    """Raised when the catalogue of the metric collectors cannot be loaded.

    Attributes:
        path (str): The catalogue file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The catalogue file.
            reason (str): Why it cannot be loaded.
        """
        self.path, self.reason = path, reason
        super().__init__(f"The metric collectors catalogue {path} cannot be loaded: {reason}")


class MarketsCatalogError(CrawlerError):
    """Raised when the catalogue of the market shares and stock values cannot be loaded.

    Attributes:
        path (str): The catalogue file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The catalogue file.
            reason (str): Why it cannot be loaded.
        """
        self.path, self.reason = path, reason
        super().__init__(f"The markets catalogue {path} cannot be loaded: {reason}")
