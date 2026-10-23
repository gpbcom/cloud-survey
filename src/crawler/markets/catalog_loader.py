from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import List, Optional, Set

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import CHRONOLOGY_PATH, MARKETS_PATH
from crawler.exception import MarketsCatalogError
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class MarketsCatalogLoader:
    """Load what the market shares and the stock values are read for (`conf/history/markets.yaml`).

    Attributes:
        logger (Logger): The loader logger.

    Notes:
        The catalogue names the companies of the chronology (`conf/history/chronology.yaml`): every company of a
        label, a listing or a valuation must be defined there, so that the charts can draw it in its colour.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _read[Model: (MarketsCatalog, Chronology)](self, path: Path, model: type[Model]) -> Model:
        """Read and validate a YAML file.

        Args:
            path (Path): The file.
            model (type[Model]): The model of its content.

        Returns:
            Model: The validated content.

        Raises:
            MarketsCatalogError: If the file cannot be read, is not valid YAML or is invalid.
        """
        try:
            with path.open(encoding="utf-8") as file:
                return model.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The markets catalogue %s cannot be read: %s", path, e.strerror)
            raise MarketsCatalogError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The markets catalogue %s is not valid YAML.", path)
            raise MarketsCatalogError(str(path), f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The markets catalogue %s is invalid (%d errors).", path, e.error_count())
            raise MarketsCatalogError(str(path), f"the content is invalid.\n{e}") from e

    def _unknown_companies(self, catalog: MarketsCatalog, companies: Set[str]) -> List[str]:
        """Get the companies the catalogue names but the chronology does not define.

        Args:
            catalog (MarketsCatalog): The catalogue.
            companies (Set[str]): The companies of the chronology.

        Returns:
            List[str]: The unknown companies, sorted, each once.
        """
        named = {entry.company for entry in catalog.labels}
        named |= {listing.company for listing in catalog.listings}
        named |= {point.company for point in catalog.valuations}
        named |= {share.company for share in catalog.manual_shares if share.company}
        return sorted(named - companies)

    ############################
    # Publicly Exposed Methods #
    ############################

    def chronology(self, path: Path = CHRONOLOGY_PATH) -> Chronology:
        """Read the chronology defining the companies (their colour, provider and country).

        Args:
            path (Path): The chronology file.

        Returns:
            Chronology: The chronology.

        Raises:
            MarketsCatalogError: If the file cannot be read or is invalid.
        """
        return self._read(path, Chronology)

    def load(self, path: Path = MARKETS_PATH, chronology_path: Path = CHRONOLOGY_PATH) -> MarketsCatalog:
        """Read and validate the catalogue, against the companies of the chronology.

        Args:
            path (Path): The catalogue file.
            chronology_path (Path): The chronology defining the companies.

        Returns:
            MarketsCatalog: The segments, areas, labels, currencies, regions, listings and valuations.

        Raises:
            MarketsCatalogError: If a file cannot be read, is invalid, or the catalogue names an unknown company.
        """
        catalog = self._read(path, MarketsCatalog)
        chronology = self.chronology(chronology_path)
        unknown = self._unknown_companies(catalog, {company.key for company in chronology.companies})
        if unknown:
            self.logger.error("The markets catalogue %s names unknown companies: %s", path, ", ".join(unknown))
            raise MarketsCatalogError(str(path), f"unknown companies (define them in the chronology): {unknown}")
        segments = {segment.key for segment in chronology.segments}
        for segment in catalog.segments:
            if segment.chronology and segment.chronology not in segments:
                self.logger.warning(
                    "The market segment %s links the unknown chronology segment %s.", segment.key, segment.chronology
                )
        self.logger.debug(
            "Markets catalogue loaded: %d segments, %d areas, %d labels, %d listings, %d valuations.",
            len(catalog.segments),
            len(catalog.areas),
            len(catalog.labels),
            len(catalog.listings),
            len(catalog.valuations),
        )
        return catalog
