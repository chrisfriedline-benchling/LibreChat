from unittest.mock import MagicMock

import pytest

from benchling_mcp_server.pubmed_client import PubMedClient
from benchling_mcp_server.server import BenchlingMCPServer


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    return MagicMock()


@pytest.fixture
def mock_benchling_client():
    """Create a mock Benchling client."""
    return MagicMock()


class MockPubMedResponse:
    """Mock response for PubMed API calls."""

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture
def mock_pubmed_client():
    """Create a mock PubMed client with configurable responses."""
    # Create a real PubMedClient instance
    client = PubMedClient()

    # Create a mock HTTP client
    mock_http_client = MagicMock()
    client.client = mock_http_client

    # Add helper methods to configure responses
    def set_pmc_response(xml_text):
        """Set the response for PMC text extraction."""
        mock_http_client.get.return_value = MockPubMedResponse(xml_text)

    def set_search_response(json_data):
        """Set the response for paper search."""
        mock_http_client.get.return_value = MockPubMedResponse(json_data)

    # Add the helper methods to the client
    client.set_pmc_response = set_pmc_response
    client.set_search_response = set_search_response

    return client


@pytest.fixture
def mock_benchling_mcp_server(mock_db_pool, mock_benchling_client, mock_pubmed_client):
    """Create a mock Benchling MCP server."""
    server = BenchlingMCPServer(
        db_pool=mock_db_pool,
        organization_id="test_org",
        benchling_client=mock_benchling_client,
        enable_literature_search=True,
    )
    server.pubmed_client = mock_pubmed_client
    return server
