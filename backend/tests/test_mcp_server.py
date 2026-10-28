from desk.mcp_server.server import mcp


async def test_server_starts_with_name() -> None:
    assert mcp.name == "desk-mcp"
    assert isinstance(await mcp.list_tools(), list)
