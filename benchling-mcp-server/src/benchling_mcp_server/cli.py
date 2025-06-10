import argparse
import logging
import os

import psycopg2
from benchling_sdk.auth.api_key_auth import ApiKeyAuth
from benchling_sdk.benchling import Benchling

from benchling_mcp_server import server
from benchling_mcp_server.pubmed_client import check_dependencies
from benchling_mcp_server.utils import load_env_file

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_env_file()


def validate_connection_string(connection_string: str) -> bool:
    return (
        connection_string.startswith("postgresql://")
        and "sslmode=verify-ca" in connection_string
    )


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchling MCP Server")
    parser.add_argument(
        "--warehouse-connection",
        "-w",
        type=str,
        help="""The PostgresSQL connection string for the Benchling Warehouse
                For example, postgres://<username>:<password>@<host>:5432/warehouse?sslmode=verify-ca
                You must have SSL certs properly configured. See https://docs.benchling.com/docs/getting-started.
                If not provided, will try to get from the BENCHLING_WAREHOUSE_CONNECTION
                environment variable or the .env file.""",
    )
    parser.add_argument(
        "--organization-id",
        "-o",
        type=str,
        help="""Queries data for the specified organization ID.
            See the organizations list in the tenant admin console (/admin) for the ID.
            If not provided, will try to get from the
            BENCHLING_ORGANIZATION_ID environment variable or the .env file.""",
    )
    parser.add_argument(
        "--benchling-api-key",
        type=str,
        help="""Benchling API key. If not provided, will try to get from the
            BENCHLING_API_KEY environment variable or the .env file.""",
    )
    parser.add_argument(
        "--benchling-base-url",
        type=str,
        help="""Benchling API base URL. If not provided, will try to get from the
            BENCHLING_API_BASE_URL environment variable or the .env file.""",
    )
    parser.add_argument(
        "--enable-literature-search",
        action="store_true",
        help="Enable Scientific Literature search tools (PubMed integration)",
        default=False,
    )
    args = parser.parse_args()
    return args


def main() -> None:
    args = get_args()
    # Get warehouse connection from args or env var
    warehouse_connection = args.warehouse_connection or os.getenv(
        "BENCHLING_WAREHOUSE_CONNECTION"
    )
    if not warehouse_connection:
        raise ValueError(
            "No warehouse connection provided. Please provide it via the \
                --warehouse-connection command line argument \
                or the BENCHLING_WAREHOUSE_CONNECTION environment variable."
        )

    if not validate_connection_string(warehouse_connection):
        raise ValueError(
            "Invalid connection string format. Must start with 'postgres://' \
                and include 'sslmode=verify-ca'"
        )

    organization_id = args.organization_id or os.getenv("BENCHLING_ORGANIZATION_ID")
    if not organization_id:
        raise ValueError(
            "No organization ID provided. Please provide it via the \
                --organization-id command line argument \
                or the BENCHLING_ORGANIZATION_ID environment variable."
        )

    try:
        logger.info("Connecting to warehouse...")
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, warehouse_connection)
        # Test connection with a simple query
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                # Set read-only transaction mode (Warehouse is read-only anyways)
                cur.execute("SET default_transaction_read_only = on")
                # Set search path to organization schema only
                cur.execute(f'SET search_path = "{organization_id}"')
                cur.execute("SELECT 1")
                cur.fetchone()
            db_pool.putconn(conn)
        logger.info("Successfully connected to warehouse")
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to warehouse: {e!s}")
        raise ValueError(f"Failed to connect to warehouse: {e!s}") from e

    benchling_api_key = args.benchling_api_key or os.getenv("BENCHLING_API_KEY")
    benchling_base_url = args.benchling_base_url or os.getenv("BENCHLING_API_BASE_URL")
    if not benchling_api_key:
        raise ValueError(
            "No Benchling API key provided. Please provide it via the \
                --benchling-api-key command line argument \
                or the BENCHLING_API_KEY environment variable."
        )
    if not benchling_base_url:
        raise ValueError(
            "No Benchling API base URL provided. Please provide it via the \
                --benchling-base-url command line argument \
                or the BENCHLING_API_BASE_URL environment variable."
        )

    if not benchling_base_url.endswith("/api/v2"):
        benchling_base_url = benchling_base_url.rstrip("/") + "/api/v2"

    benchling_client = Benchling(
        auth_method=ApiKeyAuth(benchling_api_key), url=benchling_base_url
    )
    logger.info("Benchling client initialized successfully")

    # Check if literature tools should be enabled
    enable_literature_search = args.enable_literature_search or os.getenv(
        "ENABLE_LITERATURE_SEARCH", "false"
    ).lower() in ("true", "1", "t", "y", "yes")

    if enable_literature_search:
        logger.info("Scientific Literature search tools enabled")
        missing_packages = check_dependencies()
        if missing_packages:
            logger.error(
                f"""Missing required packages for literature tools: {missing_packages}
                Please install them using: `uv pip install '.[literature-search]'`.
                Literature search tools will not be enabled.
                """
            )
    server.main(
        warehouse_connection=warehouse_connection,
        organization_id=organization_id,
        benchling_client=benchling_client,
        enable_literature_search=enable_literature_search,
    )


if __name__ == "__main__":
    main()
