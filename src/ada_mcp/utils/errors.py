"""Error handling utilities for Ada MCP Server."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from ada_mcp.als.client import LSPError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class ALSNotRunningError(Exception):
    """Raised when ALS process is not running."""

    pass


class ALSTimeoutError(Exception):
    """Raised when ALS request times out."""

    pass


def safe_tool_handler(
    fallback_factory: Callable[[], T],
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to wrap tool handlers with error handling.

    Args:
        fallback_factory: Callable that returns fallback value on error

    Returns:
        Decorated function with error handling
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                result = await func(*args, **kwargs)
                return result
            except ALSNotRunningError as e:
                logger.warning(f"ALS not running in {func.__name__}: {e}")
                return fallback_factory()
            except LSPError as e:
                logger.error(f"LSP error in {func.__name__}: {e.message}")
                return fallback_factory()
            except TimeoutError:
                logger.error(f"Timeout in {func.__name__}")
                return fallback_factory()
            except Exception as e:
                logger.exception(f"Unexpected error in {func.__name__}: {e}")
                return fallback_factory()

        return wrapper  # type: ignore

    return decorator


def format_error_response(error: str, details: str | None = None) -> dict[str, Any]:
    """
    Format an error response for MCP tool output.

    Args:
        error: Short error message
        details: Optional detailed information

    Returns:
        Dict with error information
    """
    response: dict[str, Any] = {
        "success": False,
        "error": error,
    }
    if details:
        response["details"] = details
    return response
