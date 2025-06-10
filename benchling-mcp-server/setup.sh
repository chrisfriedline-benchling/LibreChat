#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up Benchling MCP Server...${NC}"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv package installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Create and activate virtual environment
echo -e "\n${YELLOW}Creating virtual environment...${NC}"
uv venv .venv
source .venv/bin/activate

# Install dependencies
echo -e "\n${YELLOW}Installing dependencies...${NC}"
uv pip install .

# Prompt for configuration
echo -e "\n${YELLOW}Please enter your configuration details:${NC}"
while [ -z "$WAREHOUSE_CONN" ]; do
    read -p "Enter your Benchling Warehouse connection string: " WAREHOUSE_CONN
    if [ -z "$WAREHOUSE_CONN" ]; then
        echo "Benchling Warehouse connection string cannot be empty"
    fi
done

while [ -z "$ORG_ID" ]; do
    read -p "Enter your Benchling Organization ID: " ORG_ID
    if [ -z "$ORG_ID" ]; then
        echo "Benchling Organization ID cannot be empty"
    fi
done

while [ -z "$API_KEY" ]; do
    read -p "Enter your Benchling API Key: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "Benchling API key cannot be empty"
    fi
done

while [ -z "$BASE_URL" ]; do
    read -p "Enter your Benchling API Base URL: " BASE_URL
    if [ -z "$BASE_URL" ]; then
        echo "Benchling API base URL cannot be empty"
    fi
done

read -p "Enable literature search? Note that this may send data from Benchling to PubMed. (y/n): " ENABLE_LITERATURE_SEARCH
if [ "$ENABLE_LITERATURE_SEARCH" = "y" ]; then
    echo -e "\n${YELLOW}Note: You will need to run 'uv pip install ".[literature-search]"' to install optional dependencies for literature search${NC}"
fi
ENABLE_LITERATURE_SEARCH=${ENABLE_LITERATURE_SEARCH:-n}

# Write to .env
echo -e "\n${YELLOW}Creating .env file...${NC}"
echo "BENCHLING_WAREHOUSE_CONNECTION=\"$WAREHOUSE_CONN\"" > .env
echo "BENCHLING_ORGANIZATION_ID=\"$ORG_ID\"" >> .env
echo "BENCHLING_API_KEY=\"$API_KEY\"" >> .env
echo "BENCHLING_API_BASE_URL=\"$BASE_URL\"" >> .env
echo "ENABLE_LITERATURE_SEARCH=\"$ENABLE_LITERATURE_SEARCH\"" >> .env

echo -e "\n${GREEN}Setup complete!${NC}"
echo -e "You can now run the server using: ${YELLOW}uv run benchling-mcp-server${NC}"
