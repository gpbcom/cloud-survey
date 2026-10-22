from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CaBundleVariable(StrEnum):
    """Enums representing the environment variables naming the certificate bundles trusted by the HTTP clients.

    Attributes:
        REQUESTS_CA_BUNDLE (str): The bundle of `requests` (and of the libraries following it).
        CURL_CA_BUNDLE (str): The bundle of `curl` (and of `curl_cffi`).
        SSL_CERT_FILE (str): The bundle of OpenSSL.
        POC_CRAWLER_CA_BUNDLES (str): The extra bundles of this project merged into the installed one.
    """

    REQUESTS_CA_BUNDLE = "REQUESTS_CA_BUNDLE"
    CURL_CA_BUNDLE = "CURL_CA_BUNDLE"
    SSL_CERT_FILE = "SSL_CERT_FILE"
    POC_CRAWLER_CA_BUNDLES = "POC_CRAWLER_CA_BUNDLES"
