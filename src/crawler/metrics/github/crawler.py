from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Iterator

# Third Party Imports.
from pydantic import ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.enums import RequestMeta
from crawler.metrics.base import BaseMetricsCrawler, MetricFact
from crawler.metrics.github.enums import GithubField
from models.drivers.enums import MetricSource
from models.drivers.facts.repository_fact import RepositoryFact


class GithubCrawler(BaseMetricsCrawler):
    """Crawl the GitHub repositories of the providers (their Terraform provider and SDKs) for their stars.

    Attributes:
        URL (ClassVar[str]): The repository document, formatted with `owner/name`.
        REPOSITORY (ClassVar[str]): The meta key holding the repository a document describes.
        name (str): The crawler name.
        source (ClassVar[MetricSource]): GitHub.
        catalogue_url (ClassVar[str]): The GitHub API host.

    Notes:
        Without a token GitHub answers 60 requests an hour, enough for the catalogue. The token is read from the
        environment variable named by the catalogue, never from a file.
    """

    URL: ClassVar[str] = "https://api.github.com/repos/{repository}"
    REPOSITORY: ClassVar[str] = RequestMeta.METRIC_REPOSITORY
    name = "github"
    source: ClassVar[MetricSource] = MetricSource.GITHUB
    catalogue_url: ClassVar[str] = "https://api.github.com/"

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request every repository of the catalogue.

        Yields:
            Request: A request per repository.
        """
        headers = self._headers("application/vnd.github+json")
        token = self._secret(self.catalog.github_token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for entry in self.catalog.entries:
            for repository in entry.repositories:
                self.logger.debug("Requesting the GitHub repository %s of %s.", repository, entry.provider)
                yield self._metric_request(
                    self.URL.format(repository=repository), headers, entry.provider, **{self.REPOSITORY: repository}
                )

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        """Extract the stars of a repository.

        Args:
            response (Response): The repository document.

        Returns:
            Iterator[MetricFact]: The repository fact, none when the document holds no star count.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        provider = self._provider(response)
        stars = self._as_object(self._json_body(response)).get(GithubField.STARS)
        if provider is None or not isinstance(stars, int) or isinstance(stars, bool):
            self.logger.warning("The GitHub document %s holds no star count.", response.url)
            return
        try:
            yield RepositoryFact(
                provider=provider,
                repository=response.meta.get(self.REPOSITORY),
                stars=stars,
                source_url=response.url,
            )
        except ValidationError as e:
            self.logger.warning("Invalid GitHub repository %s: %s", response.url, e.errors()[0]["msg"])
