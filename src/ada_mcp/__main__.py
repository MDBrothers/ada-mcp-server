"""Entry point for running Ada MCP Server as a module."""

import asyncio
import logging
import os
import sys


def setup_logging() -> None:
    """Configure logging based on environment variable."""
    level_name = os.environ.get("ADA_MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # MCP uses stdout for protocol, logs go to stderr
    )


def main() -> None:
    """Main entry point for the Ada MCP server."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Ada MCP Server...")

    try:
        from ada_mcp.server import run_server

        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception("Server error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
