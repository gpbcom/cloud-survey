from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from sqlalchemy import MetaData, Sequence
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The base class of the tables of the crawled data.

    Attributes:
        NAMING_CONVENTION (ClassVar[Dict[str, str]]): How the indexes and constraints are named, so that the migrations
            can name them too.
        metadata (MetaData): The tables, indexes and sequences of the storage.

    Notes:
        Every row of the items tables (and every dataset) takes a new value of the `item_revision` sequence when it is
        written: the readers of a dataset read again the rows written after the revision they know.
    """

    NAMING_CONVENTION: ClassVar[Dict[str, str]] = {
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


ITEM_REVISION = Sequence("item_revision", metadata=Base.metadata)
