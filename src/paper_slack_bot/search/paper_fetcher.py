"""Paper fetcher for PubMed, bioRxiv, and arXiv."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from paper_slack_bot.storage.database import Paper

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Base class for paper fetchers."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the fetcher.

        Args:
            api_key: Optional API key for the service.
        """
        self.api_key = api_key

    @abstractmethod
    async def fetch_papers(
        self,
        keywords: list[str],
        days_back: int = 1,
        max_results: int = 100,
    ) -> list[Paper]:
        """Fetch papers matching the given criteria.

        Args:
            keywords: List of keywords to search for.
            days_back: Number of days to look back.
            max_results: Maximum number of results to return.

        Returns:
            List of Paper objects.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[Paper]:
        """Search for papers with a query string.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of Paper objects.
        """
        pass


class PubMedFetcher(BaseFetcher):
    """Fetcher for PubMed papers using NCBI E-utilities API."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async def fetch_papers(
        self,
        keywords: list[str],
        days_back: int = 1,
        max_results: int = 100,
    ) -> list[Paper]:
        """Fetch papers from PubMed.

        Args:
            keywords: List of keywords to search for.
            days_back: Number of days to look back.
            max_results: Maximum number of results.

        Returns:
            List of Paper objects.
        """
        query = " OR ".join(f'"{kw}"' for kw in keywords)
        return await self.search(query, max_results, days_back)

    async def search(
        self,
        query: str,
        max_results: int = 50,
        days_back: Optional[int] = None,
    ) -> list[Paper]:
        """Search PubMed for papers.

        Args:
            query: Search query string.
            max_results: Maximum number of results.
            days_back: Optional days to look back for date filtering.

        Returns:
            List of Paper objects.
        """
        papers = []
        try:
            # Add date filter if specified
            if days_back:
                date_from = (datetime.now() - timedelta(days=days_back)).strftime(
                    "%Y/%m/%d"
                )
                date_to = datetime.now().strftime("%Y/%m/%d")
                query = f"({query}) AND ({date_from}[PDAT] : {date_to}[PDAT])"

            # Search for paper IDs
            pmids = await self._search_pmids(query, max_results)
            if not pmids:
                return papers

            # Fetch paper details
            papers = await self._fetch_paper_details(pmids)
        except Exception as e:
            logger.error(f"Error fetching papers from PubMed: {e}")

        return papers

    async def _search_pmids(self, query: str, max_results: int) -> list[str]:
        """Search for PubMed IDs.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of PubMed IDs.
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "pub_date",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/esearch.fcgi", params=params
            ) as response:
                if response.status != 200:
                    logger.error(f"PubMed search failed: {response.status}")
                    return []
                data = await response.json()
                return data.get("esearchresult", {}).get("idlist", [])

    async def _fetch_paper_details(self, pmids: list[str]) -> list[Paper]:
        """Fetch paper details for given PubMed IDs.

        Args:
            pmids: List of PubMed IDs.

        Returns:
            List of Paper objects.
        """
        papers = []
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/efetch.fcgi", params=params
            ) as response:
                if response.status != 200:
                    logger.error(f"PubMed fetch failed: {response.status}")
                    return papers

                xml_content = await response.text()
                papers = self._parse_pubmed_xml(xml_content)

        return papers

    def _parse_pubmed_xml(self, xml_content: str) -> list[Paper]:
        """Parse PubMed XML response.

        Args:
            xml_content: XML content from PubMed API.

        Returns:
            List of Paper objects.
        """
        papers = []
        try:
            root = ET.fromstring(xml_content)
            for article in root.findall(".//PubmedArticle"):
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)
        except ET.ParseError as e:
            logger.error(f"Error parsing PubMed XML: {e}")
        return papers

    def _parse_article(self, article: ET.Element) -> Optional[Paper]:
        """Parse a single article from PubMed XML.

        Args:
            article: Article XML element.

        Returns:
            Paper object or None if parsing fails.
        """
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None

            article_elem = medline.find(".//Article")
            if article_elem is None:
                return None

            # Title
            title_elem = article_elem.find(".//ArticleTitle")
            title = title_elem.text if title_elem is not None else "No title"

            # Authors
            authors = []
            author_list = article_elem.find(".//AuthorList")
            if author_list is not None:
                for author in author_list.findall(".//Author"):
                    last_name = author.find("LastName")
                    fore_name = author.find("ForeName")
                    if last_name is not None:
                        name = last_name.text or ""
                        if fore_name is not None and fore_name.text:
                            name = f"{fore_name.text} {name}"
                        authors.append(name)

            # Abstract
            abstract_elem = article_elem.find(".//Abstract/AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else ""

            # Journal
            journal_elem = article_elem.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""

            # Publication date
            pub_date_elem = article_elem.find(".//Journal/JournalIssue/PubDate")
            pub_date = ""
            if pub_date_elem is not None:
                year = pub_date_elem.find("Year")
                month = pub_date_elem.find("Month")
                day = pub_date_elem.find("Day")
                if year is not None:
                    pub_date = year.text or ""
                    if month is not None and month.text:
                        pub_date = f"{pub_date}-{month.text}"
                        if day is not None and day.text:
                            pub_date = f"{pub_date}-{day.text}"

            # DOI and PMID
            pmid_elem = medline.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            doi = None
            for id_elem in article.findall(".//ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text
                    break

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            return Paper(
                title=title,
                authors=authors,
                abstract=abstract or "",
                doi=doi,
                journal=journal,
                publication_date=pub_date,
                url=url,
                source="pubmed",
            )
        except Exception as e:
            logger.error(f"Error parsing PubMed article: {e}")
            return None


class BioRxivFetcher(BaseFetcher):
    """Fetcher for bioRxiv preprints."""

    BASE_URL = "https://api.biorxiv.org/details/biorxiv"

    async def fetch_papers(
        self,
        keywords: list[str],
        days_back: int = 1,
        max_results: int = 100,
    ) -> list[Paper]:
        """Fetch papers from bioRxiv.

        Args:
            keywords: List of keywords to search for.
            days_back: Number of days to look back.
            max_results: Maximum number of results.

        Returns:
            List of Paper objects.
        """
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")

        papers = []
        cursor = 0

        async with aiohttp.ClientSession() as session:
            while len(papers) < max_results:
                url = f"{self.BASE_URL}/{date_from}/{date_to}/{cursor}"
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"bioRxiv fetch failed: {response.status}")
                        break

                    data = await response.json()
                    messages = data.get("messages", [])
                    if messages and "no posts" in messages[0].get("status", "").lower():
                        break

                    collection = data.get("collection", [])
                    if not collection:
                        break

                    for item in collection:
                        paper = self._parse_paper(item)
                        if paper and self._matches_keywords(paper, keywords):
                            papers.append(paper)
                            if len(papers) >= max_results:
                                break

                    cursor += len(collection)
                    if len(collection) < 100:  # bioRxiv returns max 100 per page
                        break

        return papers

    async def search(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[Paper]:
        """Search bioRxiv for papers.

        Note: bioRxiv API doesn't support direct search, so we fetch recent papers
        and filter locally.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of Paper objects.
        """
        keywords = query.lower().split()
        return await self.fetch_papers(keywords, days_back=30, max_results=max_results)

    def _parse_paper(self, item: dict) -> Optional[Paper]:
        """Parse a paper from bioRxiv API response.

        Args:
            item: Paper data from bioRxiv API.

        Returns:
            Paper object or None.
        """
        try:
            doi = item.get("doi", "")
            return Paper(
                title=item.get("title", ""),
                authors=item.get("authors", "").split("; "),
                abstract=item.get("abstract", ""),
                doi=doi,
                journal="bioRxiv",
                publication_date=item.get("date", ""),
                url=f"https://doi.org/{doi}" if doi else "",
                source="biorxiv",
            )
        except Exception as e:
            logger.error(f"Error parsing bioRxiv paper: {e}")
            return None

    def _matches_keywords(self, paper: Paper, keywords: list[str]) -> bool:
        """Check if paper matches any of the keywords.

        Args:
            paper: Paper to check.
            keywords: List of keywords.

        Returns:
            True if paper matches any keyword.
        """
        text = f"{paper.title} {paper.abstract}".lower()
        return any(kw.lower() in text for kw in keywords)


class ArxivFetcher(BaseFetcher):
    """Fetcher for arXiv preprints."""

    BASE_URL = "http://export.arxiv.org/api/query"

    async def fetch_papers(
        self,
        keywords: list[str],
        days_back: int = 1,
        max_results: int = 100,
    ) -> list[Paper]:
        """Fetch papers from arXiv.

        Args:
            keywords: List of keywords to search for.
            days_back: Number of days to look back.
            max_results: Maximum number of results.

        Returns:
            List of Paper objects.
        """
        query = " OR ".join(f'all:"{kw}"' for kw in keywords)
        return await self.search(query, max_results, days_back)

    async def search(
        self,
        query: str,
        max_results: int = 50,
        days_back: Optional[int] = None,
    ) -> list[Paper]:
        """Search arXiv for papers.

        Args:
            query: Search query string (arXiv query format).
            max_results: Maximum number of results.
            days_back: Optional days to look back.

        Returns:
            List of Paper objects.
        """
        # Convert simple query to arXiv format if needed
        if not any(
            prefix in query for prefix in ["all:", "ti:", "au:", "abs:", "cat:"]
        ):
            query = f"all:{query}"

        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        papers = []
        async with aiohttp.ClientSession() as session:
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status != 200:
                    logger.error(f"arXiv fetch failed: {response.status}")
                    return papers

                xml_content = await response.text()
                papers = self._parse_arxiv_xml(xml_content)

        # Filter by date if specified
        if days_back:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            papers = [
                p
                for p in papers
                if self._parse_date(p.publication_date) >= cutoff_date
            ]

        return papers

    def _parse_arxiv_xml(self, xml_content: str) -> list[Paper]:
        """Parse arXiv API response.

        Args:
            xml_content: XML content from arXiv API.

        Returns:
            List of Paper objects.
        """
        papers = []
        try:
            # Parse XML with namespace
            namespaces = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            root = ET.fromstring(xml_content)

            for entry in root.findall("atom:entry", namespaces):
                paper = self._parse_entry(entry, namespaces)
                if paper:
                    papers.append(paper)
        except ET.ParseError as e:
            logger.error(f"Error parsing arXiv XML: {e}")
        return papers

    def _parse_entry(
        self, entry: ET.Element, namespaces: dict[str, str]
    ) -> Optional[Paper]:
        """Parse a single entry from arXiv XML.

        Args:
            entry: Entry XML element.
            namespaces: XML namespaces.

        Returns:
            Paper object or None.
        """
        try:
            # Title
            title_elem = entry.find("atom:title", namespaces)
            title = (
                title_elem.text.replace("\n", " ").strip()
                if title_elem is not None and title_elem.text
                else ""
            )

            # Authors
            authors = []
            for author_elem in entry.findall("atom:author", namespaces):
                name_elem = author_elem.find("atom:name", namespaces)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)

            # Abstract
            summary_elem = entry.find("atom:summary", namespaces)
            abstract = (
                summary_elem.text.replace("\n", " ").strip()
                if summary_elem is not None and summary_elem.text
                else ""
            )

            # URL and DOI
            url = ""
            for link in entry.findall("atom:link", namespaces):
                if link.get("type") == "text/html":
                    url = link.get("href", "")
                    break
            if not url:
                id_elem = entry.find("atom:id", namespaces)
                url = id_elem.text if id_elem is not None and id_elem.text else ""

            # Extract arXiv ID from URL
            arxiv_id = url.split("/abs/")[-1] if "/abs/" in url else ""
            doi = f"10.48550/arXiv.{arxiv_id}" if arxiv_id else None

            # Publication date
            published_elem = entry.find("atom:published", namespaces)
            pub_date = (
                published_elem.text[:10]
                if published_elem is not None and published_elem.text
                else ""
            )

            # Categories (for journal field)
            categories = []
            for cat in entry.findall("arxiv:primary_category", namespaces):
                term = cat.get("term")
                if term:
                    categories.append(term)
            journal = f"arXiv [{', '.join(categories)}]" if categories else "arXiv"

            return Paper(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                journal=journal,
                publication_date=pub_date,
                url=url,
                source="arxiv",
            )
        except Exception as e:
            logger.error(f"Error parsing arXiv entry: {e}")
            return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            datetime object.
        """
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            return datetime.min


class PaperFetcher:
    """Unified paper fetcher for all sources."""

    def __init__(self, ncbi_api_key: Optional[str] = None):
        """Initialize the paper fetcher.

        Args:
            ncbi_api_key: Optional NCBI API key for PubMed.
        """
        self.fetchers: dict[str, BaseFetcher] = {
            "pubmed": PubMedFetcher(api_key=ncbi_api_key),
            "biorxiv": BioRxivFetcher(),
            "arxiv": ArxivFetcher(),
        }

    async def fetch_all(
        self,
        keywords: list[str],
        databases: list[str],
        days_back: int = 1,
        max_results_per_source: int = 50,
    ) -> list[Paper]:
        """Fetch papers from all specified sources.

        Args:
            keywords: List of keywords to search for.
            databases: List of databases to search (pubmed, biorxiv, arxiv).
            days_back: Number of days to look back.
            max_results_per_source: Maximum results per source.

        Returns:
            Combined list of Paper objects from all sources.
        """
        tasks = []
        for db in databases:
            if db in self.fetchers:
                tasks.append(
                    self.fetchers[db].fetch_papers(
                        keywords, days_back, max_results_per_source
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        papers = []
        for result in results:
            if isinstance(result, list):
                papers.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error fetching papers: {result}")

        return papers

    async def search(
        self,
        query: str,
        databases: list[str],
        max_results_per_source: int = 50,
    ) -> list[Paper]:
        """Search for papers across all specified sources.

        Args:
            query: Search query string.
            databases: List of databases to search.
            max_results_per_source: Maximum results per source.

        Returns:
            Combined list of Paper objects.
        """
        tasks = []
        for db in databases:
            if db in self.fetchers:
                tasks.append(self.fetchers[db].search(query, max_results_per_source))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        papers = []
        for result in results:
            if isinstance(result, list):
                papers.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error searching papers: {result}")

        return papers
