import os
from typing import Any

from fastmcp import FastMCP

from .analyzers import ANALYZERS
from .domain import CounterpartyCard

mcp = FastMCP(
    "counterparty-analysis",
    instructions="Analyze only the counterparty card supplied to each tool.",
)


def _run(name: str, card: dict[str, Any]) -> dict[str, Any]:
    validated = CounterpartyCard.model_validate(card)
    return ANALYZERS[name](validated).model_dump(mode="json")


@mcp.tool
def analyze_general(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze identity, registration status, report risk and KYC risk."""
    return _run("analyze_general", card)


@mcp.tool
def analyze_structure(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze founders, management, related companies and activities."""
    return _run("analyze_structure", card)


@mcp.tool
def analyze_legal(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze arbitration, enforcement, inspections and licenses."""
    return _run("analyze_legal", card)


@mcp.tool
def analyze_reputation(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze positive and negative reputation factors."""
    return _run("analyze_reputation", card)


@mcp.tool
def analyze_finance(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze financial dynamics and supplied financial ratios."""
    return _run("analyze_finance", card)


@mcp.tool
def analyze_procurement(card: dict[str, Any]) -> dict[str, Any]:
    """Analyze public procurement participation and signed contracts."""
    return _run("analyze_procurement", card)


def main() -> None:
    mcp.run(
        transport="http",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
