"""Tests for database module."""

import pytest
import tempfile
import os

from paper_slack_bot.storage.database import Database, Paper


class TestGetExistingDois:
    """Tests for the get_existing_dois method."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        yield db
        os.unlink(path)

    @pytest.fixture
    def sample_papers(self):
        """Create sample papers."""
        return [
            Paper(
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                doi="10.1234/paper1",
                journal="Nature",
                publication_date="2024-01-01",
                url="https://example.com/1",
                source="pubmed",
            ),
            Paper(
                title="Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                doi="10.1234/paper2",
                journal="Science",
                publication_date="2024-01-02",
                url="https://example.com/2",
                source="pubmed",
            ),
            Paper(
                title="Paper 3",
                authors=["Author 3"],
                abstract="Abstract 3",
                doi="10.1234/paper3",
                journal="Cell",
                publication_date="2024-01-03",
                url="https://example.com/3",
                source="pubmed",
            ),
        ]

    def test_get_existing_dois_empty_db(self, temp_db):
        """Test getting existing DOIs from an empty database."""
        result = temp_db.get_existing_dois(["10.1234/test1", "10.1234/test2"])

        assert result == set()

    def test_get_existing_dois_empty_list(self, temp_db):
        """Test getting existing DOIs with an empty list."""
        result = temp_db.get_existing_dois([])

        assert result == set()

    def test_get_existing_dois_some_exist(self, temp_db, sample_papers):
        """Test getting existing DOIs when some papers exist."""
        # Save some papers
        temp_db.save_papers(sample_papers[:2])

        # Check for DOIs, including some that don't exist
        dois_to_check = [
            "10.1234/paper1",  # exists
            "10.1234/paper2",  # exists
            "10.1234/paper3",  # doesn't exist (not saved)
            "10.1234/nonexistent",  # doesn't exist
        ]
        result = temp_db.get_existing_dois(dois_to_check)

        assert "10.1234/paper1" in result
        assert "10.1234/paper2" in result
        assert "10.1234/paper3" not in result
        assert "10.1234/nonexistent" not in result
        assert len(result) == 2

    def test_get_existing_dois_all_exist(self, temp_db, sample_papers):
        """Test getting existing DOIs when all papers exist."""
        temp_db.save_papers(sample_papers)

        dois_to_check = [p.doi for p in sample_papers]
        result = temp_db.get_existing_dois(dois_to_check)

        assert len(result) == 3
        for paper in sample_papers:
            assert paper.doi in result

    def test_get_existing_dois_none_exist(self, temp_db, sample_papers):
        """Test getting existing DOIs when none of the papers exist."""
        dois_to_check = ["10.1234/nonexistent1", "10.1234/nonexistent2"]
        result = temp_db.get_existing_dois(dois_to_check)

        assert result == set()


class TestPaperExists:
    """Tests for the paper_exists method."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        yield db
        os.unlink(path)

    @pytest.fixture
    def sample_paper(self):
        """Create a sample paper."""
        return Paper(
            title="Test Paper",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/test",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
        )

    def test_paper_exists_true(self, temp_db, sample_paper):
        """Test that paper_exists returns True for existing paper."""
        temp_db.save_paper(sample_paper)

        assert temp_db.paper_exists(sample_paper.doi) is True

    def test_paper_exists_false(self, temp_db):
        """Test that paper_exists returns False for non-existing paper."""
        assert temp_db.paper_exists("10.1234/nonexistent") is False


class TestSavePaperWithEmptyTitle:
    """Tests for saving papers with empty/missing titles."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        yield db
        os.unlink(path)

    def test_save_paper_with_empty_title_returns_zero(self, temp_db):
        """Test that saving a paper with empty title returns 0."""
        paper = Paper(
            title="",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/empty-title",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
        )

        result = temp_db.save_paper(paper)

        assert result == 0

    def test_save_paper_with_whitespace_title_returns_zero(self, temp_db):
        """Test that saving a paper with whitespace-only title returns 0."""
        paper = Paper(
            title="   ",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/whitespace-title",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
        )

        result = temp_db.save_paper(paper)

        assert result == 0

    def test_save_paper_with_empty_title_not_in_db(self, temp_db):
        """Test that papers with empty titles are not saved to database."""
        paper = Paper(
            title="",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/empty-title",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
        )

        temp_db.save_paper(paper)

        # The paper should not exist in the database
        assert temp_db.paper_exists(paper.doi) is False

    def test_save_papers_filters_empty_titles(self, temp_db):
        """Test that save_papers skips papers with empty titles."""
        papers = [
            Paper(
                title="Valid Paper",
                authors=["Author 1"],
                abstract="Abstract 1",
                doi="10.1234/valid",
                journal="Nature",
                publication_date="2024-01-01",
                url="https://example.com/1",
                source="pubmed",
            ),
            Paper(
                title="",
                authors=["Author 2"],
                abstract="Abstract 2",
                doi="10.1234/empty",
                journal="Science",
                publication_date="2024-01-02",
                url="https://example.com/2",
                source="pubmed",
            ),
            Paper(
                title="   ",
                authors=["Author 3"],
                abstract="Abstract 3",
                doi="10.1234/whitespace",
                journal="Cell",
                publication_date="2024-01-03",
                url="https://example.com/3",
                source="pubmed",
            ),
        ]

        ids = temp_db.save_papers(papers)

        # Only the valid paper should be saved
        assert ids[0] > 0  # Valid paper has a real ID
        assert ids[1] == 0  # Empty title returns 0
        assert ids[2] == 0  # Whitespace title returns 0

        # Only valid paper exists in the database
        assert temp_db.paper_exists("10.1234/valid") is True
        assert temp_db.paper_exists("10.1234/empty") is False
        assert temp_db.paper_exists("10.1234/whitespace") is False


class TestCleanupOldPapers:
    """Tests for the cleanup_old_papers method."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        yield db
        os.unlink(path)

    def test_cleanup_deletes_old_papers(self, temp_db):
        """Test that cleanup deletes papers older than the specified days."""
        from datetime import datetime, timedelta
        import sqlite3

        # Add a paper
        paper = Paper(
            title="Old Paper",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/old",
            journal="Nature",
            publication_date="2023-01-01",
            url="https://example.com",
            source="pubmed",
        )
        temp_db.save_paper(paper)

        # Update created_at to be 60 days ago
        conn = sqlite3.connect(temp_db.db_path)
        cursor = conn.cursor()
        old_date = datetime.now() - timedelta(days=60)
        cursor.execute('UPDATE papers SET created_at = ?',
                      (old_date.strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()

        # Cleanup papers older than 30 days
        deleted = temp_db.cleanup_old_papers(days=30)

        assert deleted == 1
        assert temp_db.paper_exists("10.1234/old") is False

    def test_cleanup_keeps_recent_papers(self, temp_db):
        """Test that cleanup keeps papers newer than the specified days."""
        # Add a paper (it will have current timestamp)
        paper = Paper(
            title="Recent Paper",
            authors=["Author"],
            abstract="Abstract",
            doi="10.1234/recent",
            journal="Nature",
            publication_date="2024-01-01",
            url="https://example.com",
            source="pubmed",
        )
        temp_db.save_paper(paper)

        # Cleanup papers older than 30 days
        deleted = temp_db.cleanup_old_papers(days=30)

        assert deleted == 0
        assert temp_db.paper_exists("10.1234/recent") is True

    def test_cleanup_with_mixed_ages(self, temp_db):
        """Test cleanup with papers of various ages."""
        from datetime import datetime, timedelta
        import sqlite3

        # Add papers
        ages = [0, 15, 29, 31, 60]  # days old
        for i, age in enumerate(ages):
            paper = Paper(
                title=f"Paper {age} days old",
                authors=["Author"],
                abstract="Abstract",
                doi=f"10.1234/paper{i}",
                journal="Nature",
                publication_date="2024-01-01",
                url="https://example.com",
                source="pubmed",
            )
            temp_db.save_paper(paper)

        # Update created_at for each paper
        conn = sqlite3.connect(temp_db.db_path)
        cursor = conn.cursor()
        for i, age in enumerate(ages):
            old_date = datetime.now() - timedelta(days=age)
            cursor.execute('UPDATE papers SET created_at = ? WHERE doi = ?',
                          (old_date.strftime('%Y-%m-%d %H:%M:%S'), f"10.1234/paper{i}"))
        conn.commit()
        conn.close()

        # Cleanup papers older than 30 days
        deleted = temp_db.cleanup_old_papers(days=30)

        # Papers 31 and 60 days old should be deleted
        assert deleted == 2
        assert temp_db.paper_exists("10.1234/paper0") is True  # 0 days
        assert temp_db.paper_exists("10.1234/paper1") is True  # 15 days
        assert temp_db.paper_exists("10.1234/paper2") is True  # 29 days
        assert temp_db.paper_exists("10.1234/paper3") is False  # 31 days
        assert temp_db.paper_exists("10.1234/paper4") is False  # 60 days
