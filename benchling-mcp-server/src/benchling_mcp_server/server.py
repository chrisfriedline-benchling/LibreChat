import json
import logging
from datetime import datetime
from typing import Any

import psycopg2
from benchling_sdk.benchling import Benchling
from mcp.server.fastmcp import Context, FastMCP
from psycopg2.pool import ThreadedConnectionPool

from benchling_mcp_server.llm_friendly_table import describe_table_to_llm
from benchling_mcp_server.pubmed_client import PubMedClient
from benchling_mcp_server.utils import _datetime_handler
from benchling_mcp_server.warehouse_overview import (
    get_warehouse_overview,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BenchlingMCPServer(FastMCP):
    """
    A MCP server for Benchling Warehouse.
    """

    def __init__(  # noqa:PLR0913
        self,
        db_pool: ThreadedConnectionPool,
        organization_id: str,
        benchling_client: Benchling,
        name: str = "benchling",
        instructions: str | None = None,
        # With Claude Desktop as the client, responses seem to truncate at 100k chars.
        # We use this to paginate the response from get_tables.
        max_response_length: int = 100000,
        query_timeout: int = 30,
        enable_literature_search: bool = False,
        **settings: Any,
    ):
        logger.info("Initializing Benchling MCP Server")
        self.db_pool = db_pool
        self.organization_id = organization_id
        self.warehouse_overview = get_warehouse_overview(db_pool, organization_id)
        # 500 characters of buffer for start/end message
        self.max_response_length = max_response_length - 500
        self.query_timeout = query_timeout
        self.benchling_client = benchling_client
        self.enable_literature_search = enable_literature_search
        self.pubmed_client = PubMedClient() if enable_literature_search else None

        super().__init__(name=name, instructions=instructions, **settings)
        logger.info("Setting up tools")
        self.setup_tools()
        logger.info("Benchling MCP Server initialized")

    async def get_notebook_entry_by_id(
        self, ctx: Context, entry_ids: list[str]
    ) -> dict:
        """
        Retrieve the notebook contents for one or more Benchling notebook entries by entry ID(s).
        Entry IDs are the IDs of the notebook entries, which must be a string that starts with `etr_`.
        If you don't have the entry IDs, you can use the get_tables and run_query tools to search for notebook entries based on their metadata.

        Args:
            entry_ids: List of Benchling entry IDs to retrieve.

        Returns:
            The JSON object(s) for the notebook entry or entries.
        """  # noqa:E501
        await ctx.info(f"Retrieving notebook entries for IDs: {entry_ids}")
        try:
            # Use bulk-get endpoint for multiple entries
            if len(entry_ids) > 1:
                entries = self.benchling_client.entries.bulk_get_entries(
                    entry_ids=entry_ids
                )
            else:
                # Single entry case
                response = self.benchling_client.entries.get_entry_by_id(
                    entry_id=entry_ids[0]
                )
                entries = [response]
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            [entry.to_dict() for entry in entries], indent=2
                        ),
                    }
                ],
                "isError": False,
            }
        except Exception as e:
            await ctx.error(f"Error retrieving notebook entries: {e!s}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error retrieving notebook entries: {e!s}",
                    }
                ],
                "isError": True,
            }

    async def run_query(self, ctx: Context, query: str) -> dict:
        """
        Runs a query on the Benchling PostgresSQL Warehouse.
        You should usually use the tools in the following order:
        1. get_tables: get all tables to understand the schema to help you construct the query.
        2. run_query: run the query you've constructed.

        Use the exact table names and field names from the list_tables tool.
        ("$raw" should not be dropped from the table names. "$" should not be dropped from the field names.)
        If the user is looking for who took an action they are probably interested in the Principal table.
        The term notebook or notebook entry refers to the entry table.
        """  # noqa:E501
        await ctx.info("Executing query")  # Log first 100 chars of query

        conn = None
        try:
            conn = self.db_pool.getconn()
            with conn.cursor() as cur:
                try:
                    # Set query timeout
                    cur.execute(
                        f"SET statement_timeout = {self.query_timeout * 1000}"
                    )  # Convert to milliseconds

                    cur.execute(query)
                    results = cur.fetchall()
                    columns = [desc[0] for desc in cur.description]

                    # Format results as a list of dictionaries
                    formatted_results = []
                    for row in results:
                        formatted_results.append(dict(zip(columns, row, strict=False)))

                    await ctx.info(f"Query returned {len(formatted_results)} rows")
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    formatted_results,
                                    indent=2,
                                    default=_datetime_handler,
                                ),
                            }
                        ],
                        "isError": False,
                    }
                except psycopg2.Error as e:
                    await ctx.error(f"Database error: {e!s}")
                    return {
                        "content": [{"type": "text", "text": f"Database error: {e!s}"}],
                        "isError": True,
                    }
                except Exception as e:
                    await ctx.error(f"Unexpected error: {e!s}")
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing query: {e!s}",
                            }
                        ],
                        "isError": True,
                    }
        finally:
            if conn is not None:
                self.db_pool.putconn(conn)

    async def get_tables(self, ctx: Context, start_index: int = 0) -> str:
        """
        Lists all tables in Benchling Warehouse. The response is limited to 100,000 characters.

        You should usually use the tools in the following order:
        1. get_tables: get all tables to understand the schema to help you construct the query.
        2. run_query: run the query you've constructed.

        All id columns are varchar unless otherwise specified.
        Not all relationships are included for each table, only specific non-obvious ones.
        """  # noqa:E501
        await ctx.info(f"Getting tables starting from index {start_index}")
        all_tables = list(self.warehouse_overview.table_info.values())
        selected_tables = []
        current_length = 0

        for table in all_tables[start_index:]:
            table_description = describe_table_to_llm(
                table,
                include_col_names=True,
                include_col_types=True,
                include_relationships=True,
                include_col_samples=True,
            )

            # Add 2 for the newlines between tables
            table_length = len(table_description) + 2

            if current_length + table_length > self.max_response_length:
                break

            selected_tables.append(table_description)
            current_length += table_length

        table_name_list = "\n\n".join(selected_tables)
        response = f"""\
The available tables (indices {start_index} to {start_index + len(selected_tables) - 1} out of {len(self.warehouse_overview.table_info)}) are:

<tables>
{table_name_list}
</tables>
"""  # noqa:E501
        assert len(response) < self.max_response_length, "Response is too long"
        await ctx.info(f"Returning {len(selected_tables)} tables")
        return response

    async def list_pubmed_papers(  # noqa:PLR0913
        self,
        ctx: Context,
        query: str,
        max_results: int = 10,
        date_range: dict[str, datetime] | None = None,
        sort_by: str = "relevance",
        article_type: str | None = None,
        journal: str | None = None,
    ) -> dict[str, Any]:
        """Search PubMed for papers matching the given query.

        Args:
            ctx: MCP context
            query: Search query string
            max_results: Maximum number of results to return (default: 10)
            date_range: Optional dictionary with 'start' and 'end' datetime objects
            sort_by: Sort results by 'relevance' or 'date' (default: 'relevance')
            article_type: Optional filter by article type
            journal: Optional filter by journal name

        Returns:
            Dictionary containing search results
            Search results will contain metadata and abstract, but will not contain full text.
            To get full text, use the get_pubmed_fulltext tool.
        """  # noqa:E501
        await ctx.info(f"Searching PubMed for: {query}")
        if not self.pubmed_client:
            await ctx.error("PubMed search is not enabled")
            return {
                "content": [{"type": "text", "text": "PubMed search is not enabled"}],
                "isError": True,
            }
        try:
            papers = self.pubmed_client.search_papers(
                query=query,
                max_results=max_results,
                date_range=date_range,
                sort_by=sort_by,
                article_type=article_type,
                journal=journal,
            )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(papers, indent=2),
                    }
                ],
                "isError": False,
            }
        except ValueError as e:
            await ctx.error(f"Invalid search parameters: {e!s}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Invalid search parameters: {e!s}",
                    }
                ],
                "isError": True,
            }
        except Exception as e:
            await ctx.error(f"Error searching PubMed: {e!s}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error searching PubMed: {e!s}",
                    }
                ],
                "isError": True,
            }

    async def get_pubmed_fulltext(self, ctx: Context, pubmed_id: str) -> dict[str, Any]:
        """
        Retrieve full text of a paper by its PubMed ID.
        This tool should only be used after list_pubmed_papers has been used to find the paper.

        Args:
            ctx: MCP context
            pubmed_id: PubMed ID of the paper

        Returns:
            Dictionary containing full text and metadata
        """  # noqa:E501
        await ctx.info(f"Retrieving full text for PubMed ID: {pubmed_id}")
        if not self.pubmed_client:
            await ctx.error("PubMed search is not enabled")
            return {
                "content": [{"type": "text", "text": "PubMed search is not enabled"}],
                "isError": True,
            }
        try:
            paper = self.pubmed_client.get_paper_fulltext(pubmed_id)

            if "error" in paper:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error retrieving paper: {paper['error']}",
                        }
                    ],
                    "isError": True,
                }

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(paper, indent=2),
                    }
                ],
                "isError": False,
            }
        except Exception as e:
            await ctx.error(f"Error retrieving paper: {e!s}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error retrieving paper: {e!s}",
                    }
                ],
                "isError": True,
            }

    def setup_tools(self) -> None:
        """
        Register the tools in the server.
        """
        # Register the tools
        self.add_tool(
            self.get_tables,
            name="get_tables",
            description="""Lists all tables in Benchling Warehouse.
                Use this tool when you need to understand the schema of the warehouse to help you construct a query.""",  # noqa:E501
        )
        self.add_tool(
            self.run_query,
            name="run_query",
            description="""Runs a query on the Benchling PostgresSQL Warehouse.
                Use this tool when you need to:
                - Access data in Benchling
                - Get a list of notebook entries""",
        )
        self.add_tool(
            self.get_notebook_entry_by_id,
            name="get_notebook_entry_by_id",
            description="""Retrieve the full JSON object for one or more Benchling notebook entries by entry ID(s).
                Use this tool when you need to get the data within a notebook entry.""",  # noqa:E501
        )

        # Register literature tools if enabled
        if self.enable_literature_search:
            logger.info("Registering Scientific Literature tools")
            self.add_tool(
                self.list_pubmed_papers,
                name="list_pubmed_papers",
                description="""Search PubMed for papers matching the given query.
                    Use this tool when you need to find scientific papers relevant to the user's query.""",  # noqa:E501
            )
            self.add_tool(
                self.get_pubmed_fulltext,
                name="get_pubmed_fulltext",
                description="""Retrieve full text of a paper by its PubMed ID.
                    Use this tool when you need to get the full text of a paper.""",
            )


def main(
    warehouse_connection: str,
    organization_id: str,
    benchling_client: Benchling,
    enable_literature_search: bool = False,
) -> None:
    db_pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=warehouse_connection,
        connect_timeout=30,
    )

    server = BenchlingMCPServer(
        db_pool=db_pool,
        organization_id=organization_id,
        benchling_client=benchling_client,
        enable_literature_search=enable_literature_search,
    )
    logger.info("Running Benchling MCP Server")
    server.run(transport="stdio")
