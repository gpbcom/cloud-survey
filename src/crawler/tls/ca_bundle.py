from __future__ import annotations

# Standard Library Imports.
import os
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import certifi

# First Party Imports.
from crawler.enums import TextEncoding
from crawler.tls.enums import CaBundleVariable


class CaBundle:
    """The certificate authorities the crawlers verify the websites with: certifi's, plus the environment's bundle.

    Attributes:
        ENVIRONMENT_VARIABLES (ClassVar[Tuple[CaBundleVariable, ...]]): The variables naming a bundle of the
            environment, which the HTTP client would otherwise use instead of certifi's.
        INSTALLED_VARIABLES (ClassVar[Tuple[CaBundleVariable, ...]]): The variables set to the merged bundle by
            `install`, read by the HTTP client when its session starts.
        SOURCES_VARIABLE (ClassVar[str]): The variable keeping the bundles of the environment once the merged one is
            installed in their place (separated by `os.pathsep`).
        CACHE_FILE (ClassVar[Path]): The default file of the merged bundle.
        ENCODING (ClassVar[str]): The encoding of the bundles.
        cache_file (Path): The file of the merged bundle.
        logger (Logger): The bundle logger.

    Notes:
        The HTTP client of the crawlers (curl_cffi) verifies the websites with the bundle named by
        `REQUESTS_CA_BUNDLE` (or `CURL_CA_BUNDLE`) when it is set, e.g. the bundle of the operating system. An outdated
        one lacks the recent roots (e.g. Sectigo Public Server Authentication Root R46, which signs scaleway.com), and
        every page of such a website fails. The merged bundle keeps the certificates of the environment (e.g. a
        company proxy authority) and adds certifi's, kept up to date with the project dependencies.
    """

    ENVIRONMENT_VARIABLES: ClassVar[Tuple[CaBundleVariable, ...]] = (
        CaBundleVariable.REQUESTS_CA_BUNDLE,
        CaBundleVariable.CURL_CA_BUNDLE,
        CaBundleVariable.SSL_CERT_FILE,
    )
    INSTALLED_VARIABLES: ClassVar[Tuple[CaBundleVariable, ...]] = (
        CaBundleVariable.REQUESTS_CA_BUNDLE,
        CaBundleVariable.CURL_CA_BUNDLE,
    )
    SOURCES_VARIABLE: ClassVar[str] = CaBundleVariable.POC_CRAWLER_CA_BUNDLES
    CACHE_FILE: ClassVar[Path] = Path.home() / ".cache" / "poc-crawler" / "ca-bundle.pem"
    ENCODING: ClassVar[str] = TextEncoding.UTF_8

    def __init__(self, cache_file: Optional[Path] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the bundle.

        Args:
            cache_file (Optional[Path]): The file of the merged bundle, `CACHE_FILE` by default.
            logger (Optional[Logger]): The bundle logger.
        """
        self.cache_file = cache_file if cache_file else self.CACHE_FILE
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CA bundle cached in %s.", self.cache_file)

    ############################
    # Internal Helpers Methods #
    ############################

    def _environment_bundles(self) -> List[Path]:
        """Get the bundles named by the environment.

        Returns:
            List[Path]: The distinct bundle files, in the order of `ENVIRONMENT_VARIABLES`, the merged bundle (already
                installed) left out.
        """
        named = [os.environ.get(variable, "").strip() for variable in self.ENVIRONMENT_VARIABLES]
        named += os.environ.get(self.SOURCES_VARIABLE, "").split(os.pathsep)
        bundles = [path for path in dict.fromkeys(Path(name) for name in named if name) if path != self.cache_file]
        self.logger.debug("%d CA bundles named by the environment.", len(bundles))
        return bundles

    def _read(self, path: Path) -> Optional[str]:
        """Read a bundle.

        Args:
            path (Path): The bundle file.

        Returns:
            Optional[str]: Its certificates, `None` when it cannot be read.
        """
        try:
            return path.read_text(encoding=self.ENCODING)
        except OSError as e:
            self.logger.warning("The CA bundle %s cannot be read, it is left out: %s", path, e)
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    def path(self) -> str:
        """Get the file of the merged bundle, written when its content changed.

        Returns:
            str: The merged bundle file, or certifi's alone when it cannot be written.
        """
        certifi_bundle = certifi.where()
        parts = [text for text in (self._read(Path(certifi_bundle)),) if text]
        for bundle in self._environment_bundles():
            text = self._read(bundle)
            if text and text not in parts:
                parts.append(text)
        merged = "\n".join(part.strip() for part in parts) + "\n"
        try:
            if not self.cache_file.is_file() or self.cache_file.read_text(encoding=self.ENCODING) != merged:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                self.cache_file.write_text(merged, encoding=self.ENCODING)
                self.logger.info("CA bundle written to %s from %d bundles.", self.cache_file, len(parts))
        except OSError as e:
            self.logger.error("The CA bundle %s cannot be written, certifi's is used alone: %s", self.cache_file, e)
            return certifi_bundle
        return str(self.cache_file)

    def install(self) -> str:
        """Make the HTTP client of the crawlers verify the websites with the merged bundle.

        Returns:
            str: The bundle file the HTTP sessions started from now on use.

        Notes:
            The merged bundle holds every certificate of the bundles it replaces: the other HTTP clients of the
            process lose none.
        """
        sources = os.pathsep.join(str(bundle) for bundle in self._environment_bundles())
        path = self.path()
        os.environ[self.SOURCES_VARIABLE] = sources
        for variable in self.INSTALLED_VARIABLES:
            os.environ[variable] = path
        self.logger.debug("CA bundle %s installed for the HTTP sessions.", path)
        return path
