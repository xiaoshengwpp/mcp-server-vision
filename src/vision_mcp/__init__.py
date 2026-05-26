"""Vision MCP Server package."""

from .config import ProviderConfig, SimpleConfig, get_config
from .server import mcp, serve

__all__ = ["mcp", "serve", "SimpleConfig", "ProviderConfig", "get_config"]
__version__ = "2.0.0"
