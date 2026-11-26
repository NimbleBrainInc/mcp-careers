"""Apply to NimbleBrain through your agent."""

from importlib.metadata import version

# The one version source is pyproject.toml; server.json restates it (a test holds them equal).
__version__ = version("mcp-careers")
