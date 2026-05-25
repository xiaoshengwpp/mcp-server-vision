"""Vision MCP Server package."""

from .server import mcp, serve
from .config import SimpleConfig, get_config

__all__ = ["mcp", "serve", "SimpleConfig", "get_config"]
__version__ = "2.0.0"
