"""Tests for Scientific Literature tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from benchling_mcp_server.pubmed_client import PubMedClient, check_dependencies
from benchling_mcp_server.server import BenchlingMCPServer


@pytest.mark.asyncio
async def test_literature_tools_registration(mock_db_pool, mock_benchling_client):
    """Test that literature tools are registered when enabled."""
    server = BenchlingMCPServer(
        db_pool=mock_db_pool,
        organization_id="test_org",
        benchling_client=mock_benchling_client,
        enable_literature_search=True,
    )
    assert server.pubmed_client is not None
    assert isinstance(server.pubmed_client, PubMedClient)
    tools = await server.list_tools()
    assert any(tool.name == "list_pubmed_papers" for tool in tools)
    assert any(tool.name == "get_pubmed_fulltext" for tool in tools)


@pytest.mark.asyncio
async def test_literature_tools_not_registered_when_disabled():
    """Test that literature tools are not registered when disabled."""
    server = BenchlingMCPServer(
        db_pool=MagicMock(),
        organization_id="test_org",
        benchling_client=MagicMock(),
        enable_literature_search=False,
    )
    assert server.pubmed_client is None
    tools = await server.list_tools()
    assert not any(tool.name == "list_pubmed_papers" for tool in tools)
    assert not any(tool.name == "get_pubmed_fulltext" for tool in tools)


def test_dependency_check():
    """Test that dependency check works correctly."""
    # Test with all dependencies available
    with patch("importlib.import_module") as mock_import:
        mock_import.return_value = MagicMock()
        missing = check_dependencies()
        assert len(missing) == 0

    # Test with missing dependencies
    with patch("importlib.import_module") as mock_import:
        mock_import.side_effect = ImportError
        missing = check_dependencies()
        assert len(missing) == 2
        assert "httpx" in missing
        assert "pypdf" in missing


@pytest.mark.asyncio
async def test_list_pubmed_papers_basic(mock_benchling_mcp_server):
    """Test basic functionality of list_pubmed_papers with required parameters."""
    # Mock the PubMed client's search_papers method
    mock_papers = [
        {
            "title": "Test Paper 1",
            "abstract": "Test Abstract 1",
            "pub_date": "2024-01-01",
            "pubmed_id": "12345",
            "authors": ["Author 1", "Author 2"],
        }
    ]
    mock_benchling_mcp_server.pubmed_client.search_papers = MagicMock(
        return_value=mock_papers
    )

    # Test basic search
    result = await mock_benchling_mcp_server.list_pubmed_papers(
        ctx=AsyncMock(),
        query="test query",
    )

    assert not result["isError"]
    assert "content" in result
    assert len(result["content"]) == 1
    assert "text" in result["content"][0]
    assert "Test Paper 1" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_list_pubmed_papers_error_handling(mock_db_pool, mock_benchling_client):
    """Test error handling in list_pubmed_papers."""
    server = BenchlingMCPServer(
        db_pool=mock_db_pool,
        organization_id="test_org",
        benchling_client=mock_benchling_client,
        enable_literature_search=True,
    )

    # Test ValueError handling
    server.pubmed_client.search_papers = MagicMock(
        side_effect=ValueError("Invalid parameters")
    )
    result = await server.list_pubmed_papers(
        ctx=AsyncMock(),
        query="test query",
    )
    assert result["isError"]
    assert "Invalid parameters" in result["content"][0]["text"]

    # Test general exception handling
    server.pubmed_client.search_papers = MagicMock(
        side_effect=Exception("Unexpected error")
    )
    result = await server.list_pubmed_papers(
        ctx=AsyncMock(),
        query="test query",
    )
    assert result["isError"]
    assert "Unexpected error" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_list_pubmed_papers_disabled(mock_db_pool, mock_benchling_client):
    """Test list_pubmed_papers when literature tools are disabled."""
    server = BenchlingMCPServer(
        db_pool=mock_db_pool,
        organization_id="test_org",
        benchling_client=mock_benchling_client,
        enable_literature_search=False,
    )

    result = await server.list_pubmed_papers(
        ctx=AsyncMock(),
        query="test query",
    )
    assert result["isError"]
    assert "PubMed search is not enabled" in result["content"][0]["text"]
