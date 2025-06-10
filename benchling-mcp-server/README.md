# Benchling MCP Server

A [Model Control Protocol (MCP)](https://modelcontextprotocol.io/introduction) server that connects to the [Benchling](https://benchling.com/) Warehouse and API, allowing you to query your Benchling data using natural language.
This server is read-only, meaning it cannot create, update, or delete any objects in Benchling.

> **Note**
> This is a prototype and *is not recommended for production usage*.

This repository is an example of how to set up a Benchling MCP server.

## Prerequisites

- Python 3.10 or higher
- `uv` [installed](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL client libraries
- Access to a Benchling Warehouse
- Organization ID from your Benchling tenant
- A Benchling API Key

## 🚀 Quickstart

1. **Clone the repo and enter the directory:**
   ```bash
   git clone git@github.com:Benchling-Labs/benchling-mcp-server.git
   cd benchling-mcp-server
   ```

2. **Run the setup script:**
   ```bash
   ./setup.sh
   ```
Fill in the appropriate environment variables when prompted.

3. **Run the server:**
   ```bash
   uv run benchling-mcp-server
   ```

If this completes without an error, you have successfully set up your MCP server!

4. **Configure your MCP Client**

**If using Claude Desktop (recommended):**
Make sure you have downloaded [Claude Desktop](https://claude.ai/download).

You'll need to edit your `claude_desktop_config.json`. You can find [where this is](https://modelcontextprotocol.io/quickstart/user#2-add-the-filesystem-mcp-server) by going to `Settings > Developer > Edit Config` on Claude Desktop.

On Mac, it should look something like `/Users/<username>/Library/Application Support/Claude/claude_desktop_config.json`

Then, update it to contain the following definition (replacing the variable parts as appropriate). To find your path to `uv`, you can run `which uv`.
```json
{
   "mcpServers": {
      "benchling-mcp-server": {
         "command": "<path_to_uv>",
         "args": [
            "--directory",
            "<installation_path>",
            "run",
            "benchling-mcp-server"
         ]
      }
   }
}
```

### Super fast quickstart
Alternatively, if you don't want to do any steps, you can just paste the following into your `claude_desktop_config.json` (see above for instructions on how to find):
```
{
  "mcpServers": {
    "benchling-mcp-server-public": {
      "command": "/path/to/uvx",
      "args": [
        "--from",
        "git+ssh://git@github.com/Benchling-Labs/benchling-mcp-server@main",
        "benchling-mcp-server"
      ],
      "env": {
        "BENCHLING_WAREHOUSE_CONNECTION": "<WAREHOUSE_CONNECTION>",
        "BENCHLING_ORGANIZATION_ID": "<ORG_ID>",
        "BENCHLING_API_KEY": "<API_KEY>",
        "BENCHLING_API_BASE_URL": "<TENANT>"
        "ENABLE_LITERATURE_SEARCH": "false"
      }
    }
  }
}
```

*If you are using an MCP client other than Claude Desktop, please follow that tool's installation guide.*

## 🔨 Available Tools

Currently available tools:
| **Category** | **Enabled by default** | **Tool** | **Description** |
| ------------ | --------------------- | -------- | --------------- |
| **Benchling Warehouse** | Yes | `get_tables` | Lists all tables in Benchling Warehouse |
| **Benchling Warehouse** | Yes | `run_query` | Runs a query on the Benchling PostgresSQL Warehouse |
| **Benchling API** | Yes | `get_notebook_entry_by_id` | Retrieve the full JSON object for one or more Benchling notebook entries based on entry ID(s) |
| **Scientific Literature** | No | `list_pubmed_papers` | Search PubMed for scientific papers matching a query |
| **Scientific Literature** | No | `get_pubmed_fulltext` | Retrieve full text of a paper by its PubMed ID |

This MCP server is still a work in progress, and we plan to add more tools in the future.


### Enabling Literature Tools
The Scientific Literature tools provide access to PubMed's database of scientific papers. These tools are optional and must be explicitly enabled.
This allows the MCP server to send queries to PubMed and retrieve papers that may be relevant to your work in Benchling.

To enable the Scientific Literature tools, you must:

1. Install dependencies
```bash
uv pip install ".[literature-search]"
```

2. Either use the command line flag:
   ```bash
   uv run benchling-mcp-server --enable-literature-search
   ```

   OR

   Set the environment variable:
   ```bash
   export ENABLE_LITERATURE_SEARCH=true
   ```

## Detailed step-by-step installation guide
If you're having trouble with the [quickstart guide above](#quickstart), here is a more detailed walkthrough:

### Environment Variables
The recommended configuration of the server is done using environment variables:

| Name                           | Required? | Description                                                | Where to find                                    | Example Value |
|-------------------------------|-----------|------------------------------------------------------------|-------------------------------------------------|--------------|
| `BENCHLING_WAREHOUSE_CONNECTION` | Yes       | Connection URL of the Benchling Postgres Warehouse         | If you don't already have credentials, you can [follow these directions](https://docs.benchling.com/docs/getting-started#obtaining-credentials) to get set up. Make sure you're [using SSL](https://docs.benchling.com/docs/getting-started#configuring-postgresql-clients-for-security) (sslmode=verify-ca) when connecting.                     | `postgres://<username>:<password>@<host>:5432/warehouse?sslmode=verify-ca` |
| `BENCHLING_ORGANIZATION_ID`      | Yes       | Your Benchling Organization ID. You might need to replace `-` with `_`.      | See the organizations list in the tenant admin console (/admin) for the ID.                        | `acmebio` |
| `BENCHLING_API_KEY`             | Yes        | API Key for accessing the Benchling API                    | Go to your Settings in Benchling and scroll to the bottom to see API Keys ([instructions](https://docs.benchling.com/docs/getting-started-1#setup))| `sk_XXXXXXXXXXXXXXXX` |
| `BENCHLING_API_BASE_URL`        | Yes        | Base URL for the Benchling API (e.g. https://<your domain>.benchling.com/api/v2) | The URL in your browser when accessing Benchling | `https://acme.benchling.com/api/v2` |
| `ENABLE_LITERATURE_SEARCH`      | No        | Enable Scientific Literature tools                         | Set to "true" to enable literature tools         | `true` |

Place the correct values of these into your `.env` file.

### Installation
1. Clone this repository:
```bash
git clone git@github.com:Benchling-Labs/benchling-mcp-server.git
cd benchling-mcp-server
```

2. Ensure `uv` is [installed](https://docs.astral.sh/uv/getting-started/installation/)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Use `uv` to install dependencies:
```
uv venv .venv
uv pip install .
```

4. Copy the `.env.template` file to `.env` and fill out the appropriate environment variables

5. Run `uv run benchling-mcp-server --help` to confirm installation and see all available options:

```bash
Usage: benchling-mcp-server [OPTIONS]

Options:
  -w, --warehouse-connection TEXT  PostgreSQL connection string
  -o, --organization-id TEXT   Benchling organization id
  --benchling-api-key TEXT         Benchling API key
  --benchling-base-url TEXT        Benchling API base URL
  --enable-literature-search (optional)       Enable Scientific Literature search tools (PubMed integration)
  --log-level [DEBUG|INFO|WARNING|ERROR]
                                  Set logging level
  --log-json                      Output logs in JSON format
  --help                          Show this message and exit.
```

### Usage
To run the MCP server, you can just run the following from within your installation directory:
```
uv run benchling-mcp-server
```

Then follow your preferred MCP client's setup instructions.
Here we show an example with [Claude Desktop](https://claude.ai/download).
You'll need to edit your `claude_desktop_config.json`. You can find [where this is](https://modelcontextprotocol.io/quickstart/user#2-add-the-filesystem-mcp-server) by going to `Settings > Developer > Edit Config` on Claude Desktop.

On Mac, it should look something like `/Users/<username>/Library/Application Support/Claude/claude_desktop_config.json

Then, update it to contain the following definition (replacing the variable parts as appropriate). To find your path to `uv`, you can run `which uv`.
```json
{
   "mcpServers": {
      "benchling-mcp-server": {
         "command": "<path_to_uv>",
         "args": [
            "--directory",
            "<installation_path>",
            "run",
            "benchling-mcp-server"
         ]
      }
   }
}
```

## Troubleshooting

### Common Issues

1. Warehouse Connection Issues:
   - Verify your connection string format
   - Ensure SSL certificates are properly configured
   - Check network connectivity to the warehouse

2. Organization Id Issues:
   - Verify the organization id in your Benchling tenant admin console
   - Ensure you have proper permissions for the organization

3. API Credential Issues:
   - Verify your API key has the necessary permissions
   - Ensure the base URL is correct for your tenant
   - Check that both API key and base URL are provided

4. Claude Desktop Issues:
   - Ensure Claude Desktop has the correct path to `uv`
   - Ensure the installation path points to the correct folder
   - If you made modifications to this code, you'll need to exit Claude Desktop and restart it to see changes

5. Literature Tools Issues:
   - Ensure you have installed the optional dependencies with `uv pip install ".[literature-search]"`
   - Verify that the tools are enabled either via CLI flag or environment variable
   - Check that you have internet connectivity for PubMed API access

## Limitations

This is a research prototype and not intended for product usage.

It only supports the `stdio` protocol, meaning it is only suited for local use.

## Disclaimers
> **Warning**
MCP servers allow natural language queries against your data. While this server only supports read-only operations, you should carefully evaluate the security implications of deploying any MCP server in your environment. Use at your own risk.


## Support

For support, please contact ai-ml@benchling.com
