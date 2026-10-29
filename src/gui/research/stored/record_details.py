from __future__ import annotations

# Standard Library Imports.
from html import escape
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QTextBrowser

# First Party Imports.
from models.companies.enums import PatentCitationKind
from models.companies.stored.papers.stored_paper import StoredPaper
from models.companies.stored.patents.patent_file import PatentFile


class RecordDetails(QTextBrowser):
    """The detail pane of the Stored data: everything stored about the record selected, its links clickable.

    Attributes:
        PATENT_PAGE (ClassVar[str]): The Google Patents page of a publication.
        CITATIONS (ClassVar[List[Tuple[PatentCitationKind, str]]]): The direction of each kind of citation, in the
            order they are listed.
        MAX_CITATIONS (ClassVar[int]): The citations listed of each kind (the rest is counted).
        logger (Logger): The pane logger.

    Notes:
        The pane is read-only: a link opens in the system browser.
    """

    PATENT_PAGE: ClassVar[str] = "https://patents.google.com/patent/{number}/en"
    CITATIONS: ClassVar[List[Tuple[PatentCitationKind, str]]] = [
        (PatentCitationKind.CITES, "Cites"),
        (PatentCitationKind.CITED_BY, "Cited by"),
        (PatentCitationKind.FAMILY_CITES, "Family cites"),
        (PatentCitationKind.FAMILY_CITED_BY, "Family cited by"),
    ]
    MAX_CITATIONS: ClassVar[int] = 100

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build an empty pane.

        Args:
            logger (Optional[Logger]): The pane logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setOpenExternalLinks(True)
        self.setPlaceholderText("Select a row to see everything stored about it.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _anchor(self, url: Optional[str], text: str) -> str:
        """Write a link.

        Args:
            url (Optional[str]): The page, no link when `None`.
            text (str): The text shown.

        Returns:
            str: The HTML of the link.
        """
        return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>' if url else escape(text)

    def _fields(self, fields: Sequence[Tuple[str, str]]) -> str:
        """Write labelled values, the empty ones left out.

        Args:
            fields (Sequence[Tuple[str, str]]): The label and the HTML value of each field.

        Returns:
            str: The HTML of the table.
        """
        rows = "".join(f"<tr><td><b>{escape(label)}</b></td><td>{value}</td></tr>" for label, value in fields if value)
        return f"<table cellspacing='4'>{rows}</table>"

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_message(self, message: str) -> None:
        """Show a message instead of a record.

        Args:
            message (str): The message.
        """
        self.logger.debug("Details message: %s", message)
        self.setHtml(f"<p><i>{escape(message)}</i></p>")

    def show_fields(self, title: str, fields: Sequence[Tuple[str, str]], link: Optional[str]) -> None:
        """Show a record of a profile or a window: its columns, labelled.

        Args:
            title (str): The record's name.
            fields (Sequence[Tuple[str, str]]): The title and the text of each column.
            link (Optional[str]): The page the record is opened at.
        """
        self.logger.debug("Details of %s shown.", title)
        body = self._fields([(label, escape(value)) for label, value in fields])
        self.setHtml(f"<h3>{self._anchor(link, title)}</h3>{body}")

    def show_patent(self, file: PatentFile) -> None:
        """Show everything stored about a publication.

        Args:
            file (PatentFile): The publication, its people, classes and citations.
        """
        patent = file.patent
        number = patent.publication_number
        self.logger.debug("Details of the patent %s shown: %d citations.", number, len(file.citations))
        head = self._fields(
            [
                ("Assignee", escape(patent.assignee or "")),
                ("Filed by", escape(", ".join(file.assignees_original))),
                ("Held by", escape(", ".join(file.assignees_current))),
                ("Inventors", escape(", ".join(file.inventors))),
                ("Priority", patent.priority_date.isoformat() if patent.priority_date else ""),
                ("Published", patent.publication_date.isoformat() if patent.publication_date else ""),
                ("Granted", patent.grant_date.isoformat() if patent.grant_date else ""),
                ("Family", escape(patent.family_id or "")),
                ("Claims", str(patent.claims) if patent.claims is not None else ""),
                ("CPC classes", escape(", ".join(file.cpc))),
                ("Companies", escape(", ".join(patent.companies))),
            ]
        )
        parts = [f"<h3>{self._anchor(self.PATENT_PAGE.format(number=number), number)}</h3>"]
        if patent.title:
            parts.append(f"<p><b>{escape(patent.title)}</b></p>")
        parts.append(head)
        if file.abstract:
            parts.append(f"<p>{escape(file.abstract)}</p>")
        if not patent.page_read:
            parts.append("<p><i>Its page was not read yet: no citations, classes or family.</i></p>")
        for kind, label in self.CITATIONS:
            cited = [citation for citation in file.citations if citation.kind is kind]
            if not cited:
                continue
            items = "".join(
                "<li>"
                + self._anchor(self.PATENT_PAGE.format(number=citation.publication_number), citation.publication_number)
                + (f" ({citation.priority_date.isoformat()})" if citation.priority_date else "")
                + (f" {escape(citation.assignee)}" if citation.assignee else "")
                + (f": {escape(citation.title)}" if citation.title else "")
                + (" <i>examiner</i>" if citation.examiner else "")
                + "</li>"
                for citation in cited[: self.MAX_CITATIONS]
            )
            more = f"<p>… and {len(cited) - self.MAX_CITATIONS} more.</p>" if len(cited) > self.MAX_CITATIONS else ""
            parts.append(f"<h4>{label} ({len(cited)})</h4><ul>{items}</ul>{more}")
        self.setHtml("".join(parts))

    def show_paper(self, paper: StoredPaper) -> None:
        """Show everything stored about a paper, its authors and their institutions.

        Args:
            paper (StoredPaper): The paper, with its authors.
        """
        self.logger.debug("Details of the paper %s shown: %d authors.", paper.openalex_id, len(paper.authors))
        head = self._fields(
            [
                ("Published", paper.publication_date.isoformat() if paper.publication_date else ""),
                ("Venue", escape(paper.venue or "")),
                ("Type", escape(paper.type or "")),
                ("Topic", escape(paper.topic or "")),
                ("Citations", str(paper.cited_by_count)),
                ("FWCI", f"{paper.fwci:.2f}" if paper.fwci is not None else ""),
                ("Open access", "yes" if paper.is_oa else "no"),
                ("DOI", self._anchor(paper.link(), paper.doi) if paper.doi else ""),
                ("OpenAlex", self._anchor(f"https://openalex.org/{paper.openalex_id}", paper.openalex_id)),
                ("Companies", escape(", ".join(paper.companies))),
            ]
        )
        authors = "".join(
            "<li>"
            + self._anchor(f"https://openalex.org/{author.author_id}" if author.author_id else None, author.name)
            + (" <b>(company)</b>" if author.company_affiliated else "")
            + (f" ORCID {escape(author.orcid)}" if author.orcid else "")
            + (
                " — "
                + ", ".join(
                    self._anchor(f"https://openalex.org/{institution}", institution)
                    for institution in author.institutions
                )
                if author.institutions
                else ""
            )
            + "</li>"
            for author in paper.authors
        )
        title = self._anchor(paper.link(), paper.title or paper.openalex_id)
        self.setHtml(f"<h3>{title}</h3>{head}<h4>Authors ({len(paper.authors)})</h4><ul>{authors}</ul>")
