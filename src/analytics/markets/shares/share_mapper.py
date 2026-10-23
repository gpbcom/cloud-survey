from __future__ import annotations

# Standard Library Imports.
import re
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Pattern, Sequence, Set, Tuple

# First Party Imports.
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.markets.catalog.share_segment import ShareSegment
from models.markets.enums import Device, Granularity, ShareSource, StatCounterStat
from models.markets.facts.release_share import ReleaseShare
from models.markets.facts.share_observation import ShareObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.market_share_value import MarketShareValue
from models.stats.market_report import MarketReport


class ShareMapper:
    """Turn the shares as the sources print them into the stored market shares of the chronology's companies.

    Attributes:
        PERIOD (ClassVar[Pattern[str]]): The format of a Synergy period: a year, or a year and a quarter.
        REGIONS (ClassVar[Dict[MarketRegion, str]]): The area of each Synergy region.
        catalog (MarketsCatalog): The segments, and the company behind each label.
        logger (Logger): The mapper logger.

    Notes:
        - A StatCounter share goes to the segment reading its statistic. Its label is kept as printed, and the
          company behind it is set from the catalogue (`Chrome` is Google), `None` for a label of no company.
        - A Synergy report gives the cloud segment one share per player and quarter, worldwide or in Europe. The
          aggregates (the big three, the European providers…) are left out: their members are listed, and the
          shares of a period must not count anyone twice. The half-years are left out (they overlap the quarters).
    """

    PERIOD: ClassVar[Pattern[str]] = re.compile(r"^(\d{4})(?:Q([1-4]))?$")
    REGIONS: ClassVar[Dict[MarketRegion, str]] = {MarketRegion.WORLDWIDE: "ww", MarketRegion.EUROPE: "eu"}

    def __init__(self, catalog: MarketsCatalog, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            catalog (MarketsCatalog): The segments, and the company behind each label.
            logger (Optional[Logger]): The mapper logger.
        """
        self.catalog = catalog
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _segments_by_stat(self) -> Dict[StatCounterStat, ShareSegment]:
        """Get the segment reading each StatCounter statistic.

        Returns:
            Dict[StatCounterStat, ShareSegment]: The segment of each statistic of the catalogue.
        """
        return {segment.stat: segment for segment in self.catalog.statcounter_segments() if segment.stat}

    def _synergy_period(self, period: str) -> Optional[Tuple[date, Granularity]]:
        """Read a Synergy period.

        Args:
            period (str): The period, `2026Q2` or `2024` (a half-year is not read).

        Returns:
            Optional[Tuple[date, Granularity]]: Its first day and its kind, `None` for a half-year.
        """
        found = self.PERIOD.match(period)
        if found is None:
            return None
        year, quarter = int(found.group(1)), found.group(2)
        if quarter is None:
            return date(year, 1, 1), Granularity.YEAR
        return date(year, 3 * int(quarter) - 2, 1), Granularity.QUARTER

    ############################
    # Publicly Exposed Methods #
    ############################

    def statcounter(self, observations: Sequence[ShareObservation]) -> List[MarketShareValue]:
        """Map StatCounter shares to their segment and company.

        Args:
            observations (Sequence[ShareObservation]): The shares as StatCounter prints them.

        Returns:
            List[MarketShareValue]: The market shares, those of a statistic no segment reads left out.
        """
        segments = self._segments_by_stat()
        values: List[MarketShareValue] = []
        unread: Set[str] = set()
        for observation in observations:
            segment = segments.get(observation.stat)
            if segment is None:
                unread.add(observation.stat.value)
                continue
            values.append(
                MarketShareValue(
                    segment=segment.key,
                    area=observation.area,
                    period=observation.month,
                    granularity=Granularity.MONTH,
                    metric=segment.metric,
                    device=observation.device,
                    source=ShareSource.STATCOUNTER,
                    label=observation.label,
                    company=self.catalog.company_of(ShareSource.STATCOUNTER, observation.label),
                    value=observation.value,
                    source_url=observation.source_url,
                )
            )
        if unread:
            self.logger.warning("StatCounter statistics read by no segment: %s.", ", ".join(sorted(unread)))
        self.logger.debug("%d StatCounter shares mapped.", len(values))
        return values

    def synergy(self, reports: Sequence[MarketReport]) -> List[MarketShareValue]:
        """Turn the Synergy cloud infrastructure reports into market shares.

        Args:
            reports (Sequence[MarketReport]): The stored Synergy reports.

        Returns:
            List[MarketShareValue]: A share per player (aggregates left out), quarter or year, and region.
        """
        segment = next((entry for entry in self.catalog.segments if entry.source is ShareSource.SYNERGY), None)
        if segment is None:
            self.logger.warning("No segment of the markets catalogue reads Synergy: its reports are left out.")
            return []
        values: List[MarketShareValue] = []
        for report in reports:
            period = self._synergy_period(report.period)
            if report.segment is not MarketSegment.CLOUD_INFRASTRUCTURE or period is None:
                continue
            aggregates: Set[MarketPlayer] = {share.part_of for share in report.shares if share.part_of}
            for share in report.shares:
                if share.player in aggregates:
                    continue
                label = "Others" if share.player is MarketPlayer.OTHERS else share.player.value
                values.append(
                    MarketShareValue(
                        segment=segment.key,
                        area=self.REGIONS[report.region],
                        period=period[0],
                        granularity=period[1],
                        metric=segment.metric,
                        device=Device.ALL,
                        source=ShareSource.SYNERGY,
                        label=label,
                        company=self.catalog.company_of(ShareSource.SYNERGY, share.player.value),
                        value=share.share_pct,
                        estimate=share.approximate or share.computed,
                        source_url=report.source_url,
                    )
                )
        self.logger.debug("%d Synergy cloud shares mapped from %d reports.", len(values), len(reports))
        return values

    def releases(self, shares: Sequence[ReleaseShare]) -> List[MarketShareValue]:
        """Turn the shares of analyst press releases into market shares of the chronology's companies.

        Args:
            shares (Sequence[ReleaseShare]): The shares as the releases state them.

        Returns:
            List[MarketShareValue]: The market shares, those of a segment the catalogue does not define left out.

        Notes:
            A period stated by several releases (the quarter, then the same quarter a year later as the year-ago
            column, with another top 5) takes the shares of a single release: the one whose shares sum closest to
            100% (the most complete), the one published last on a tie. Mixing them would count two top 5s.
        """
        values: List[MarketShareValue] = []
        unknown: Set[str] = set()
        releases: Dict[Tuple[ShareSource, str, str, date, Granularity], Dict[Tuple[str, date], List[ReleaseShare]]] = (
            defaultdict(lambda: defaultdict(list))
        )
        for share in shares:
            period = (share.source, share.segment, share.area, share.period, share.granularity)
            releases[period][(share.source_url, share.published)].append(share)
        chosen: List[ReleaseShare] = []
        for stated in releases.values():
            best = min(
                stated.items(),
                key=lambda item: (abs(sum(share.value for share in item[1]) - 100.0), -item[0][1].toordinal()),
            )
            chosen.extend({share.label: share for share in best[1]}.values())
        for share in chosen:
            segment = self.catalog.segment(share.segment)
            if segment is None:
                unknown.add(share.segment)
                continue
            values.append(
                MarketShareValue(
                    segment=segment.key,
                    area=share.area,
                    period=share.period,
                    granularity=share.granularity,
                    metric=segment.metric,
                    device=Device.ALL,
                    source=share.source,
                    label=share.label,
                    company=self.catalog.company_of(share.source, share.label),
                    value=share.value,
                    source_url=share.source_url,
                )
            )
        if unknown:
            self.logger.warning("Release shares of unknown segments left out: %s.", ", ".join(sorted(unknown)))
        self.logger.debug("%d release shares mapped.", len(values))
        return values

    def manual(self) -> List[MarketShareValue]:
        """Turn the shares of the source dossier typed in the catalogue into market shares.

        Returns:
            List[MarketShareValue]: A share per entry, those of a segment the catalogue does not define left out.
        """
        values: List[MarketShareValue] = []
        for share in self.catalog.manual_shares:
            segment = self.catalog.segment(share.segment)
            if segment is None:
                self.logger.warning("Manual share of the unknown segment %s left out.", share.segment)
                continue
            period, granularity = share.start()
            values.append(
                MarketShareValue(
                    segment=segment.key,
                    area=share.area,
                    period=period,
                    granularity=granularity,
                    metric=segment.metric,
                    device=Device.ALL,
                    source=ShareSource.MANUAL,
                    label=share.label,
                    company=share.company,
                    value=share.value,
                    source_url=f"{share.source} [{share.tag}]",
                )
            )
        self.logger.debug("%d manual shares mapped.", len(values))
        return values
