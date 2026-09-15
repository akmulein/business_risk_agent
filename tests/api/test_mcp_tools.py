import pytest
from fastmcp import Client

from app.analysis.service import TOOL_NAMES
from app.domain import ChapterResult
from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_mcp_exposes_and_executes_all_six_tools(card):
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == set(TOOL_NAMES)
        for name in TOOL_NAMES:
            result = await client.call_tool(
                name, {"card": card.model_dump(mode="json")}
            )
            chapter = ChapterResult.model_validate(result.data)
            assert chapter.chapter == name.removeprefix("analyze_")
            assert chapter.conclusion
            assert chapter.error is None
