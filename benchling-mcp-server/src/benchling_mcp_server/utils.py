import logging
import os
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _datetime_handler(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def find_env_file() -> Path | None:
    """Find the .env file in the current directory or any parent directory."""
    current_dir = Path.cwd()
    while current_dir != current_dir.root:
        env_path = current_dir / ".env"
        if env_path.exists():
            return env_path
        current_dir = current_dir.parent
    return None


def load_env_file(override: bool = False) -> None:
    """Load environment variables from a .env file."""
    env_path = find_env_file()
    if env_path is None or not env_path.exists():
        logger.debug(f"No .env file found at {env_path}")
        return

    try:
        with open(env_path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                # Split on first equals sign
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key in os.environ and not override:
                        continue
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]

                    if value is not None:
                        os.environ[key] = value
        logger.info("Loaded environment variables from .env file")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {e!s}")
