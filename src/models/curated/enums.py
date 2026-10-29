from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum


class CuratedDataset(StrEnum):
    """Enums representing a section of the chronology or of the markets catalogue, stored as curated records.

    Attributes:
        CHRONOLOGY_AS_OF (str): The month the chronology is written as of.
        CHRONOLOGY_SEGMENTS (str): The segments of the chronology.
        CHRONOLOGY_COMPANIES (str): The companies of the chronology (every company key).
        CHRONOLOGY_REIGNS (str): The leaders of each segment, with their dates.
        CHRONOLOGY_EVENTS (str): The notable events (policy shocks, launches, deals).
        MARKETS_SEGMENTS (str): The markets followed.
        MARKETS_AREAS (str): The countries and regions the shares are read for.
        MARKETS_LABELS (str): The company of each label of a source.
        MARKETS_CURRENCIES (str): The FRED series of each currency.
        MARKETS_COUNTRY_CURRENCIES (str): The currency of each country.
        MARKETS_REGIONS (str): The regions, by their countries.
        MARKETS_LISTINGS (str): The stock listings of the companies.
        MARKETS_VALUATIONS (str): The valuations of the private companies.
        MARKETS_PRESS (str): The press searches of the shares.
        MARKETS_PRESS_NAMES (str): The other names the press gives the companies.
        MARKETS_MANUAL_SHARES (str): The shares typed by hand, each with its source.
        LAUNCH_ALIASES (str): The names a dated source gives a catalogue product.
    """

    CHRONOLOGY_AS_OF = "chronology-as-of"
    CHRONOLOGY_SEGMENTS = "chronology-segments"
    CHRONOLOGY_COMPANIES = "chronology-companies"
    CHRONOLOGY_REIGNS = "chronology-reigns"
    CHRONOLOGY_EVENTS = "chronology-events"
    MARKETS_SEGMENTS = "markets-segments"
    MARKETS_AREAS = "markets-areas"
    MARKETS_LABELS = "markets-labels"
    MARKETS_CURRENCIES = "markets-currencies"
    MARKETS_COUNTRY_CURRENCIES = "markets-country-currencies"
    MARKETS_REGIONS = "markets-regions"
    MARKETS_LISTINGS = "markets-listings"
    MARKETS_VALUATIONS = "markets-valuations"
    MARKETS_PRESS = "markets-press"
    MARKETS_PRESS_NAMES = "markets-press-names"
    MARKETS_MANUAL_SHARES = "markets-manual-shares"
    LAUNCH_ALIASES = "launch-aliases"


class CuratedFile(StrEnum):
    """Enums representing a file of the curated bundle (`data/curated/<file>.json`).

    Attributes:
        CHRONOLOGY (str): The chronology.
        MARKETS (str): The markets catalogue.
        COMPANIES (str): The companies crawled and their identifiers.
        FIGURES (str): The figures researched by hand.
        LAUNCHES (str): The launch dates of the cloud products.
    """

    CHRONOLOGY = "chronology"
    MARKETS = "markets"
    COMPANIES = "companies"
    FIGURES = "figures"
    LAUNCHES = "launches"


class RecordOrigin(StrEnum):
    """Enums representing where a curated row comes from.

    Attributes:
        SEED (str): The bundle (the research written down).
        USER (str): A person, in the explorer or by an import.
        RESOLVER (str): An identity resolver (a candidate until confirmed).
        PARSER (str): A parser of the cited document (it confirmed the curated value).
    """

    SEED = "seed"
    USER = "user"
    RESOLVER = "resolver"
    PARSER = "parser"


class IdentifierKind(StrEnum):
    """Enums representing what an identifier of a company identifies it at.

    Attributes:
        SEC_CIK (str): A SEC filer.
        PATENT_ASSIGNEE (str): An assignee name searched on Google Patents.
        PATENT_EXCLUDE (str): A pattern of the homonym assignees left out.
        OPENALEX_INSTITUTION (str): An OpenAlex institution.
        OPENALEX_INCLUDE (str): A pattern an affiliation text resolved to the company must match.
        OPENALEX_EXCLUDE (str): A pattern of the homonym affiliation texts left out.
    """

    SEC_CIK = "sec-cik"
    PATENT_ASSIGNEE = "patent-assignee"
    PATENT_EXCLUDE = "patent-exclude"
    OPENALEX_INSTITUTION = "openalex-institution"
    OPENALEX_INCLUDE = "openalex-include"
    OPENALEX_EXCLUDE = "openalex-exclude"


class IdentifierStatus(StrEnum):
    """Enums representing whether an identifier is used.

    Attributes:
        CONFIRMED (str): Used by the crawls.
        CANDIDATE (str): Found by a resolver, waiting for a person's review.
        REJECTED (str): Refused by a person (a resolver never proposes it again).
    """

    CONFIRMED = "confirmed"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class FigureCheck(StrEnum):
    """Enums representing what a parser of the cited document found for a researched fiscal year.

    Attributes:
        UNCHECKED (str): No parser read its document.
        MATCH (str): The document states the same figures.
        MISMATCH (str): The document states other figures (the researched ones are kept).
        UNPARSED (str): The document could not be read by a parser.
    """

    UNCHECKED = "unchecked"
    MATCH = "match"
    MISMATCH = "mismatch"
    UNPARSED = "unparsed"
