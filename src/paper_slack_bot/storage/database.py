"""SQLite database storage for Paper Slack Bot."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Optional


@dataclass
class Paper:
    """Represents a scientific paper."""

    title: str
    authors: list[str]
    abstract: str
    doi: Optional[str]
    journal: str
    publication_date: str
    url: str
    source: str  # pubmed, biorxiv, arxiv
    relevance_score: Optional[float] = None
    relevance_explanation: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert paper to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "doi": self.doi,
            "journal": self.journal,
            "publication_date": self.publication_date,
            "url": self.url,
            "source": self.source,
            "relevance_score": self.relevance_score,
            "relevance_explanation": self.relevance_explanation,
            "created_at": self.created_at,
        }


@dataclass
class SearchQuery:
    """Represents a search query history entry."""

    query: str
    filters: dict[str, Any]
    result_count: int
    user_id: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class UserPreference:
    """Represents user preferences."""

    user_id: str
    preferred_journals: list[str] = field(default_factory=list)
    subscribed_keywords: list[str] = field(default_factory=list)
    id: Optional[int] = None
    updated_at: Optional[str] = None


class Database:
    """SQLite database manager for Paper Slack Bot."""

    def __init__(self, db_path: str | Path = "papers.db"):
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Papers table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    abstract TEXT,
                    doi TEXT UNIQUE,
                    journal TEXT,
                    publication_date TEXT,
                    url TEXT,
                    source TEXT,
                    relevance_score REAL,
                    relevance_explanation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Search history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    filters TEXT,
                    result_count INTEGER,
                    user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # User preferences table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    preferred_journals TEXT,
                    subscribed_keywords TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)"
            )

    def save_paper(self, paper: Paper) -> int:
        """Save a paper to the database.

        Args:
            paper: Paper object to save.

        Returns:
            ID of the saved paper.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if paper with same DOI exists
            if paper.doi:
                cursor.execute("SELECT id FROM papers WHERE doi = ?", (paper.doi,))
                existing = cursor.fetchone()
                if existing:
                    return existing["id"]

            cursor.execute(
                """
                INSERT INTO papers (
                    title, authors, abstract, doi, journal,
                    publication_date, url, source, relevance_score,
                    relevance_explanation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    paper.title,
                    json.dumps(paper.authors),
                    paper.abstract,
                    paper.doi,
                    paper.journal,
                    paper.publication_date,
                    paper.url,
                    paper.source,
                    paper.relevance_score,
                    paper.relevance_explanation,
                ),
            )
            return cursor.lastrowid or 0

    def save_papers(self, papers: list[Paper]) -> list[int]:
        """Save multiple papers to the database.

        Args:
            papers: List of Paper objects to save.

        Returns:
            List of IDs of saved papers.
        """
        return [self.save_paper(paper) for paper in papers]

    def get_paper_by_doi(self, doi: str) -> Optional[Paper]:
        """Get a paper by its DOI.

        Args:
            doi: DOI of the paper.

        Returns:
            Paper object if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers WHERE doi = ?", (doi,))
            row = cursor.fetchone()
            if row:
                return self._row_to_paper(row)
            return None

    def paper_exists(self, doi: str) -> bool:
        """Check if a paper with given DOI exists.

        Args:
            doi: DOI of the paper.

        Returns:
            True if paper exists, False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,))
            return cursor.fetchone() is not None

    def get_existing_dois(self, dois: list[str]) -> set[str]:
        """Check which DOIs already exist in the database.

        Args:
            dois: List of DOIs to check.

        Returns:
            Set of DOIs that already exist in the database.
        """
        if not dois:
            return set()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Use parameterized query with IN clause
            placeholders = ",".join("?" * len(dois))
            cursor.execute(
                f"SELECT doi FROM papers WHERE doi IN ({placeholders})",
                dois,
            )
            return {row["doi"] for row in cursor.fetchall()}

    def get_recent_papers(
        self, days: int = 7, source: Optional[str] = None
    ) -> list[Paper]:
        """Get papers from the last N days.

        Args:
            days: Number of days to look back.
            source: Optional source filter (pubmed, biorxiv, arxiv).

        Returns:
            List of Paper objects.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff_date = datetime.now() - timedelta(days=days)

            if source:
                cursor.execute(
                    """
                    SELECT * FROM papers
                    WHERE created_at >= ? AND source = ?
                    ORDER BY created_at DESC
                """,
                    (cutoff_date.isoformat(), source),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM papers
                    WHERE created_at >= ?
                    ORDER BY created_at DESC
                """,
                    (cutoff_date.isoformat(),),
                )

            return [self._row_to_paper(row) for row in cursor.fetchall()]

    def search_papers(
        self,
        query: str,
        limit: int = 50,
    ) -> list[Paper]:
        """Search papers by title or abstract.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching Paper objects.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{query}%"
            cursor.execute(
                """
                SELECT * FROM papers
                WHERE title LIKE ? OR abstract LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (search_pattern, search_pattern, limit),
            )
            return [self._row_to_paper(row) for row in cursor.fetchall()]

    def save_search_query(self, search: SearchQuery) -> int:
        """Save a search query to history.

        Args:
            search: SearchQuery object to save.

        Returns:
            ID of the saved search query.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO search_history (query, filters, result_count, user_id)
                VALUES (?, ?, ?, ?)
            """,
                (
                    search.query,
                    json.dumps(search.filters),
                    search.result_count,
                    search.user_id,
                ),
            )
            return cursor.lastrowid or 0

    def get_search_history(
        self, user_id: Optional[str] = None, limit: int = 50
    ) -> list[SearchQuery]:
        """Get search history.

        Args:
            user_id: Optional user ID to filter by.
            limit: Maximum number of results.

        Returns:
            List of SearchQuery objects.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    """
                    SELECT * FROM search_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (user_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM search_history
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            return [self._row_to_search_query(row) for row in cursor.fetchall()]

    def save_user_preference(self, pref: UserPreference) -> int:
        """Save or update user preferences.

        Args:
            pref: UserPreference object to save.

        Returns:
            ID of the saved preference.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_preferences (user_id, preferred_journals, subscribed_keywords)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_journals = excluded.preferred_journals,
                    subscribed_keywords = excluded.subscribed_keywords,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    pref.user_id,
                    json.dumps(pref.preferred_journals),
                    json.dumps(pref.subscribed_keywords),
                ),
            )
            return cursor.lastrowid or 0

    def get_user_preference(self, user_id: str) -> Optional[UserPreference]:
        """Get user preferences.

        Args:
            user_id: User ID to look up.

        Returns:
            UserPreference object if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_user_preference(row)
            return None

    def cleanup_old_papers(self, days: int = 30) -> int:
        """Remove papers older than N days.

        Args:
            days: Number of days to keep papers.

        Returns:
            Number of deleted papers.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff_date = datetime.now() - timedelta(days=days)
            cursor.execute(
                "DELETE FROM papers WHERE created_at < ?", (cutoff_date.isoformat(),)
            )
            return cursor.rowcount

    def _row_to_paper(self, row: sqlite3.Row) -> Paper:
        """Convert database row to Paper object."""
        return Paper(
            id=row["id"],
            title=row["title"],
            authors=json.loads(row["authors"]),
            abstract=row["abstract"] or "",
            doi=row["doi"],
            journal=row["journal"] or "",
            publication_date=row["publication_date"] or "",
            url=row["url"] or "",
            source=row["source"] or "",
            relevance_score=row["relevance_score"],
            relevance_explanation=row["relevance_explanation"],
            created_at=row["created_at"],
        )

    def _row_to_search_query(self, row: sqlite3.Row) -> SearchQuery:
        """Convert database row to SearchQuery object."""
        return SearchQuery(
            id=row["id"],
            query=row["query"],
            filters=json.loads(row["filters"]) if row["filters"] else {},
            result_count=row["result_count"],
            user_id=row["user_id"],
            created_at=row["created_at"],
        )

    def _row_to_user_preference(self, row: sqlite3.Row) -> UserPreference:
        """Convert database row to UserPreference object."""
        return UserPreference(
            id=row["id"],
            user_id=row["user_id"],
            preferred_journals=(
                json.loads(row["preferred_journals"])
                if row["preferred_journals"]
                else []
            ),
            subscribed_keywords=(
                json.loads(row["subscribed_keywords"])
                if row["subscribed_keywords"]
                else []
            ),
            updated_at=row["updated_at"],
        )
