from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CrawlSource(StrEnum):
    """Enums representing what a run of the crawler does (`CRAWLER_SOURCE`).

    Attributes:
        CATALOGUE (str): Crawl the product catalogues.
        MARKETPLACE (str): Crawl the marketplace software.
        BOTH (str): Crawl the catalogues, then the marketplaces.
        RECLASSIFY (str): Classify the stored marketplace software again, without crawling.
        STATISTICS (str): Crawl the cloud market statistics (Synergy Research Group).
        IMPORT_JSON (str): Import the JSON files of the former file storage into the database.
        TRANSLATE (str): Translate the pending source labels, categorize the unclassified items, then match the
            equivalent catalogue services, with the language model (`conf/llm.yaml`), without crawling.
        CORRESPOND (str): Match the equivalent catalogue services of the providers with the language model only.
        METRICS (str): Compute the measures of the providers (the criteria of the driver analysis) again.
    """

    CATALOGUE = "catalogue"
    MARKETPLACE = "marketplace"
    BOTH = "both"
    RECLASSIFY = "reclassify"
    STATISTICS = "statistics"
    IMPORT_JSON = "import-json"
    TRANSLATE = "translate"
    CORRESPOND = "correspond"
    METRICS = "metrics"


@unique
class HtmlAttribute(StrEnum):
    """Enums representing the HTML attributes read by the crawlers on the scraped elements.

    Attributes:
        HREF (str): The target of a link.
        CLASS (str): The CSS classes of an element.
        ID (str): The identifier of an element.
        TITLE (str): The title (tooltip) of an element.
        NAME (str): The name of a `meta` (or form) element.
        PROPERTY (str): The property of an Open Graph `meta` element.
        CONTENT (str): The value of a `meta` element.
        SRC (str): The source of an image or a script.
        ALT (str): The alternative text of an image.
    """

    HREF = "href"
    CLASS = "class"
    ID = "id"
    TITLE = "title"
    NAME = "name"
    PROPERTY = "property"
    CONTENT = "content"
    SRC = "src"
    ALT = "alt"


@unique
class HttpMethod(StrEnum):
    """Enums representing the HTTP methods of the requests sent by the crawlers.

    Attributes:
        GET (str): Read a resource.
        POST (str): Send a query (e.g. the search body of a marketplace API).
    """

    GET = "GET"
    POST = "POST"


@unique
class RequestMeta(StrEnum):
    """Enums representing the meta keys the crawlers attach to their requests, read back with the responses.

    Attributes:
        PAGE_DATES (str): Marks a sitemap request read for the last modification of its pages.
        PRODUCT_PAGE (str): Marks a product page request, holding the requested URL.
        PRODUCT_NAME (str): Holds the product name given by a listing.
        PRODUCT_UPDATED (str): Holds the last modification of a product page given by a sitemap.
        PRODUCT_CATEGORIES (str): Holds the catalogue categories of a product page given by a listing.
        MAY_BE_EMPTY (str): Marks a marketplace page which may legitimately hold no software.
        METRIC_PROVIDER (str): Holds the provider a metric source document is read for.
        METRIC_REPOSITORY (str): Holds the GitHub repository a document describes.
    """

    PAGE_DATES = "page_dates"
    PRODUCT_PAGE = "product_page"
    PRODUCT_NAME = "product_name"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_CATEGORIES = "product_categories"
    MAY_BE_EMPTY = "may_be_empty"
    METRIC_PROVIDER = "metric_provider"
    METRIC_REPOSITORY = "metric_repository"


@unique
class PageMetaName(StrEnum):
    """Enums representing the `name` (or Open Graph `property`) of the `meta` tags read on the product pages.

    Attributes:
        DESCRIPTION (str): The page description.
        OG_TITLE (str): The Open Graph title.
        OG_DESCRIPTION (str): The Open Graph description.
        OG_UPDATED_TIME (str): The Open Graph last modification.
        ARTICLE_PUBLISHED_TIME (str): The publication date of an article page.
        ARTICLE_MODIFIED_TIME (str): The last modification of an article page.
        DATE_PUBLISHED (str): The schema.org publication date.
        DATE_MODIFIED (str): The schema.org last modification.
        CPP_LAST_MODIFIED_TIME (str): The last modification given by some content platforms (e.g. Tencent Cloud).
    """

    DESCRIPTION = "description"
    OG_TITLE = "og:title"
    OG_DESCRIPTION = "og:description"
    OG_UPDATED_TIME = "og:updated_time"
    ARTICLE_PUBLISHED_TIME = "article:published_time"
    ARTICLE_MODIFIED_TIME = "article:modified_time"
    DATE_PUBLISHED = "datePublished"
    DATE_MODIFIED = "dateModified"
    CPP_LAST_MODIFIED_TIME = "cpp-last-modified-time"


@unique
class TextEncoding(StrEnum):
    """Enums representing the text encodings and decoding error policies of the crawled documents.

    Attributes:
        UTF_8 (str): The UTF-8 encoding.
        REPLACE (str): Replace the undecodable bytes rather than failing.
    """

    UTF_8 = "utf-8"
    REPLACE = "replace"
