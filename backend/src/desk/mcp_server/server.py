"""`desk-mcp` entry point (stdio). Tools and `--groups` access control arrive in Stage 4.2."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "desk-mcp",
    instructions="Crypto Desk analytics: prices, indicators, cycles, stats, on-chain and macro.",
)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
