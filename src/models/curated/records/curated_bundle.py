from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.curated.companies.company_identifier import CompanyIdentifier
from models.curated.companies.company_profile import CompanyProfile
from models.curated.figures.reported_company_record import ReportedCompanyRecord
from models.curated.figures.reported_event_record import ReportedEventRecord
from models.curated.figures.reported_year_record import ReportedYearRecord
from models.curated.launches.product_launch import ProductLaunch
from models.curated.records.curated_record import CuratedRecord


class CuratedBundle(BaseModel):
    """Every curated row: what seeds a database, and what an export writes back (`data/curated/*.json`).

    Attributes:
        records (List[CuratedRecord]): The sections of the chronology and of the markets catalogue.
        profiles (List[CompanyProfile]): The companies crawled.
        identifiers (List[CompanyIdentifier]): Their identifiers at the sources.
        figure_companies (List[ReportedCompanyRecord]): The companies whose figures were researched.
        figure_years (List[ReportedYearRecord]): The fiscal years researched.
        figure_events (List[ReportedEventRecord]): The dated figures researched.
        launches (List[ProductLaunch]): The curated launches of the cloud products.
    """

    records: List[CuratedRecord] = Field(default_factory=list, description="The chronology and markets sections.")
    profiles: List[CompanyProfile] = Field(default_factory=list, description="The companies crawled.")
    identifiers: List[CompanyIdentifier] = Field(default_factory=list, description="Their identifiers.")
    figure_companies: List[ReportedCompanyRecord] = Field(default_factory=list, description="The researched companies.")
    figure_years: List[ReportedYearRecord] = Field(default_factory=list, description="The researched fiscal years.")
    figure_events: List[ReportedEventRecord] = Field(default_factory=list, description="The researched events.")
    launches: List[ProductLaunch] = Field(default_factory=list, description="The curated launches.")
