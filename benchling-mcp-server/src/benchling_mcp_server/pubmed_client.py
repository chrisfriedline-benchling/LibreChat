"""PubMed API client for scientific literature tools."""

import importlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

MAX_PUBMED_RESULTS = 100


REQUIRED_PACKAGES = [
    "httpx",
    "pypdf",
]


def check_dependencies() -> list[str]:
    """Check if all required packages are installed.

    Returns:
        List of missing package names
    """
    missing_packages = []
    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
        except ImportError:
            missing_packages.append(package)
            logger.error(f"Missing required package: {package}")

    return missing_packages


class PubMedClient:
    """Client for interacting with PubMed's E-utilities API."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    PMC_BASE_URL = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
    VALID_SORT_OPTIONS: ClassVar[set[str]] = {"relevance", "date"}
    VALID_ARTICLE_TYPES: ClassVar[set[str]] = {
        "clinical trial",
        "review",
        "meta-analysis",
        "case report",
        "letter",
        "editorial",
        "comment",
        "systematic review",
    }

    def __init__(self) -> None:
        """Initialize the PubMed client."""
        self.client = httpx.Client()

    def _validate_search_params(
        self,
        max_results: int,
        sort_by: str,
        article_type: str | None,
        journal: str | None,
    ) -> None:
        """Validate search parameters.

        Args:
            max_results: Maximum number of results to return
            sort_by: Sort results by 'relevance' or 'date'
            article_type: Optional filter by article type
            journal: Optional filter by journal name

        Raises:
            ValueError: If any parameter is invalid
        """
        if max_results <= 0:
            raise ValueError("max_results must be greater than 0")
        if max_results > MAX_PUBMED_RESULTS:
            raise ValueError(f"max_results cannot exceed {MAX_PUBMED_RESULTS}")

        if sort_by not in self.VALID_SORT_OPTIONS:
            raise ValueError(
                f"Invalid sort_by value. Must be one of: {', '.join(self.VALID_SORT_OPTIONS)}"  # noqa:E501
            )

        if article_type and article_type.lower() not in self.VALID_ARTICLE_TYPES:
            raise ValueError(
                f"Invalid article_type. Must be one of: {', '.join(self.VALID_ARTICLE_TYPES)}"  # noqa:E501
            )

        if journal and len(journal.strip()) == 0:
            raise ValueError("journal cannot be empty")

    def search_papers(  # noqa:PLR0913
        self,
        query: str,
        max_results: int = 10,
        date_range: dict[str, datetime] | None = None,
        sort_by: str = "relevance",
        article_type: str | None = None,
        journal: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search PubMed for papers matching the given query.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            date_range: Optional dictionary with 'start' and 'end' datetime objects
            sort_by: Sort results by 'relevance' or 'date'
            article_type: Optional filter by article type
            journal: Optional filter by journal name

        Returns:
            List of dictionaries containing paper information

        Raises:
            ValueError: If any parameter is invalid
        """
        # Validate parameters
        self._validate_search_params(max_results, sort_by, article_type, journal)

        # Build the search query
        search_params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        }

        # Add date range if provided
        if date_range:
            if "start" in date_range:
                search_params["mindate"] = date_range["start"].strftime("%Y/%m/%d")
            if "end" in date_range:
                search_params["maxdate"] = date_range["end"].strftime("%Y/%m/%d")

        # Add sorting
        if sort_by == "date":
            search_params["sort"] = "date"
        else:  # relevance is default
            search_params["sort"] = "relevance"

        # Add filters
        if article_type:
            search_params["term"] = (
                str(search_params["term"]) + f" AND {article_type}[Publication Type]"
            )
        if journal:
            search_params["term"] = (
                str(search_params["term"]) + f" AND {journal}[Journal]"
            )

        try:
            # First, search for papers
            search_url = f"{self.BASE_URL}/esearch.fcgi"
            response = self.client.get(search_url, params=search_params)
            response.raise_for_status()
            search_results = response.json()

            # Get paper details
            if (
                "esearchresult" in search_results
                and "idlist" in search_results["esearchresult"]
            ):
                paper_ids = search_results["esearchresult"]["idlist"]
                return self._get_paper_details(paper_ids)
            return []

        except httpx.RequestError as e:
            logger.error(f"Error searching PubMed: {e!s}")
            raise ValueError(f"Error searching PubMed: {e!s}") from e

    def _get_pmc_id(self, pubmed_id: str) -> str | None:
        """Get the PubMed Central ID for a given PubMed ID.

        Args:
            pubmed_id: PubMed ID of the paper

        Returns:
            PubMed Central ID if available, None otherwise
        """
        try:
            fetch_url = f"{self.BASE_URL}/elink.fcgi"
            fetch_params = {
                "dbfrom": "pubmed",
                "db": "pmc",
                "id": pubmed_id,
                "retmode": "json",
            }
            response = self.client.get(fetch_url, params=fetch_params)
            response.raise_for_status()
            result = response.json()

            if result.get("linksets"):
                linkset = result["linksets"][0]
                if linkset.get("linksetdbs"):
                    linksetdb = linkset["linksetdbs"][0]
                    if linksetdb.get("links"):
                        return str(linksetdb["links"][0])
            return None
        except httpx.RequestError as e:
            logger.error(f"Error getting PMC ID: {e!s}")
            return None

    def _get_plaintext_from_pmc(self, pmc_id: str) -> str | None:
        """Get plaintext full text from PubMed Central.

        Args:
            pmc_id: PubMed Central ID of the paper

        Returns:
            Plaintext content if available, None otherwise
        """
        try:
            fetch_url = f"{self.PMC_BASE_URL}"
            fetch_params = {
                "verb": "GetRecord",
                "identifier": f"oai:pubmedcentral.nih.gov:{pmc_id}",
                "metadataPrefix": "pmc",
            }
            response = self.client.get(fetch_url, params=fetch_params)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)

            # Define namespace map
            namespaces = {
                "jats": "https://jats.nlm.nih.gov/ns/archiving/1.3/",
                "xlink": "http://www.w3.org/1999/xlink",
                "mml": "http://www.w3.org/1998/Math/MathML",
                "ali": "http://www.niso.org/schemas/ali/1.0/",
            }

            # Extract text from all sections
            text_content = []

            # Get abstract if available
            abstract = root.find(".//jats:abstract", namespaces)
            if abstract is not None:
                for p in abstract.findall(".//jats:p", namespaces):
                    text_content.append("".join(p.itertext()))

            # Get main body content
            body = root.find(".//jats:body", namespaces)
            if body is not None:
                # Extract text from all sections
                for sec in body.findall(".//jats:sec", namespaces):
                    # Get section title if available
                    title = sec.find("jats:title", namespaces)
                    if title is not None:
                        text_content.append("".join(title.itertext()))

                    # Get paragraphs in section
                    for p in sec.findall(".//jats:p", namespaces):
                        text_content.append("".join(p.itertext()))

            return "\n\n".join(text_content) if text_content else None

        except httpx.RequestError as e:
            logger.error(f"Error getting plaintext from PMC: {e!s}")
            return None

    def _parse_pdf(self, pdf_url: str) -> str | None:
        """Parse PDF content from a URL.

        Args:
            pdf_url: URL of the PDF file

        Returns:
            Extracted text content if successful, None otherwise
        """
        from pypdf import PdfReader

        try:
            response = self.client.get(pdf_url)
            response.raise_for_status()

            # Read PDF from bytes
            pdf_file = BytesIO(response.content)
            reader = PdfReader(pdf_file)

            # Extract text from all pages
            text_content = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_content.append(text)

            return "\n\n".join(text_content) if text_content else None
        except Exception as e:
            logger.error(f"Error parsing PDF: {e!s}")
            return None

    def get_paper_fulltext(self, pubmed_id: str) -> dict[str, Any]:
        """Retrieve full text of a paper by its PubMed ID.

        Args:
            pubmed_id: PubMed ID of the paper

        Returns:
            Dictionary containing full text and metadata
        """
        try:
            # First get paper details
            details = self._get_paper_details([pubmed_id])
            if not details:
                return {
                    "error": "Paper not found",
                    "pubmed_id": pubmed_id,
                    "available_content": "none",
                }

            paper = details[0]
            paper["pubmed_id"] = pubmed_id  # Ensure pubmed_id is included

            # Try to get PMC ID
            pmc_id = self._get_pmc_id(pubmed_id)
            if pmc_id:
                # Try to get plaintext from PMC
                plaintext = self._get_plaintext_from_pmc(pmc_id)
                if plaintext:
                    paper["full_text"] = plaintext
                    paper["full_text_source"] = "PMC"
                    paper["available_content"] = "full_text"
                    return paper

            # If no plaintext available, get full text links
            fetch_url = f"{self.BASE_URL}/efetch.fcgi"
            fetch_params = {
                "db": "pubmed",
                "id": pubmed_id,
                "retmode": "xml",
            }
            response = self.client.get(fetch_url, params=fetch_params)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)

            # Extract full text links
            full_text_links = []
            pdf_links = []

            # Get PMC links
            for article_id in root.findall(".//ArticleId[@IdType='pmc']"):
                if article_id.text:
                    full_text_links.append(
                        {
                            "type": "PMC",
                            "url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{article_id.text}/",
                        }
                    )

            # Get PDF links
            for link in root.findall(".//Link"):
                url = link.get("URL")
                if link.get("Provider") == "DOI" and url:
                    full_text_links.append(
                        {
                            "type": "DOI",
                            "url": url,
                        }
                    )
                    pdf_links.append(url)

            # Try to parse PDF if available
            for pdf_url in pdf_links:
                pdf_text = self._parse_pdf(pdf_url)
                if pdf_text:
                    paper["full_text"] = pdf_text
                    paper["full_text_source"] = "PDF"
                    paper["available_content"] = "full_text"
                    paper["full_text_links"] = full_text_links
                    return paper

            # If no full text available, use abstract
            paper["full_text"] = paper.get("abstract", "")
            paper["full_text_source"] = "abstract"
            paper["available_content"] = "abstract"
            paper["full_text_links"] = full_text_links

            return paper

        except httpx.RequestError as e:
            logger.error(f"Error retrieving paper: {e!s}")
            return {
                "error": str(e),
                "pubmed_id": pubmed_id,
                "available_content": "none",
            }
        except Exception as e:
            logger.error(f"Unexpected error retrieving paper: {e!s}")
            return {
                "error": f"Unexpected error: {e!s}",
                "pubmed_id": pubmed_id,
                "available_content": "none",
            }

    def _get_paper_details(self, paper_ids: list[str]) -> list[dict[str, Any]]:
        """Get detailed information for a list of paper IDs.

        Args:
            paper_ids: List of PubMed IDs

        Returns:
            List of dictionaries containing paper details
        """
        try:
            fetch_url = f"{self.BASE_URL}/efetch.fcgi"
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(paper_ids),
                "retmode": "xml",
            }
            response = self.client.get(fetch_url, params=fetch_params)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)
            papers = []

            for article in root.findall(".//PubmedArticle"):
                paper = {
                    "pubmed_id": article.findtext(".//PMID", ""),
                    "title": article.findtext(".//ArticleTitle", ""),
                    "abstract": article.findtext(".//AbstractText", ""),
                    "authors": [
                        {
                            "last_name": author.findtext(".//LastName", ""),
                            "first_name": author.findtext(".//ForeName", ""),
                        }
                        for author in article.findall(".//Author")
                    ],
                    "journal": {
                        "name": article.findtext(".//Journal/Title", ""),
                        "volume": article.findtext(".//Volume", ""),
                        "issue": article.findtext(".//Issue", ""),
                        "pages": article.findtext(".//MedlinePgn", ""),
                    },
                    "publication_date": self._parse_date(article),
                }
                papers.append(paper)

            return papers

        except httpx.RequestError as e:
            logger.error(f"Error fetching paper details: {e!s}")
            return []

    def _parse_date(self, article: ET.Element) -> str:
        """Parse publication date from article XML.

        Args:
            article: XML element containing article data

        Returns:
            Formatted date string
        """
        pub_date = article.find(".//PubDate")
        if pub_date is None:
            return ""

        date_parts = []
        for part in ["Year", "Month", "Day"]:
            element = pub_date.find(part)
            if element is not None and element.text:
                date_parts.append(element.text)

        return "-".join(date_parts) if date_parts else ""
