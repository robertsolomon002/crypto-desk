"""One-tool FastMCP stdio server for the Stage 0.3 langchain-mcp-adapters round trip."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("probe-dummy")


@mcp.tool()
def echo_add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
