from __future__ import annotations

# Third Party Imports.
from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentClassificationRow(Base):
    """A CPC class of a publication.

    Attributes:
        publication_number (Mapped[str]): The publication.
        cpc (Mapped[str]): The class, e.g. `G06N3/08`.
        main (Mapped[bool]): Whether it is the publication's main class.
    """

    __tablename__ = StorageTable.PATENT_CLASSIFICATIONS
    __table_args__ = (Index("ix_patent_classifications_cpc", "cpc"),)

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    cpc: Mapped[str] = mapped_column(String(20), primary_key=True)
    main: Mapped[bool] = mapped_column(Boolean)
