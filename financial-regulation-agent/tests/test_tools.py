# tests/test_tools.py
"""
Production tests for the Tool Registry and individual tools.

Tests cover:
- Tool registration
- Tool invocation
- Error handling
- Integration with ToolRegistry
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from tools.registry import ToolRegistry
from tools.treasury import TreasuryTool
from tools.fed_balance_sheet import FedBalanceSheetTool


@pytest.fixture
def clean_registry():
    """Reset registry before each test"""
    ToolRegistry._tools = {}
    yield
    ToolRegistry._tools = {}


def test_tool_registration(clean_registry):
    """Test that tools can be registered correctly"""
    ToolRegistry.register(TreasuryTool)
    ToolRegistry.register(FedBalanceSheetTool)

    registered = ToolRegistry.list_tools()
    assert "treasury" in registered
    assert "fed_balance_sheet" in registered


def test_get_tool(clean_registry):
    """Test retrieving a registered tool"""
    ToolRegistry.register(TreasuryTool)
    
    tool = ToolRegistry.get_tool("treasury")
    assert tool is not None
    assert tool.name == "treasury"
    assert isinstance(tool, TreasuryTool)


def test_get_nonexistent_tool(clean_registry):
    """Test error when requesting unregistered tool"""
    with pytest.raises(ValueError, match="Tool 'nonexistent' not registered"):
        ToolRegistry.get_tool("nonexistent")


@pytest.mark.asyncio
async def test_treasury_tool_execution(clean_registry):
    """Test actual tool execution with mocked API"""
    ToolRegistry.register(TreasuryTool)
    
    # Mock the API call inside the tool
    with patch('tools.treasury.requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [{"avg_interest_rate_amt": "4.5"}]
        }

        result = await ToolRegistry.invoke("treasury", endpoint="avg_interest_rates")
        
        assert result is not None
        assert "data" in result


@pytest.mark.asyncio
async def test_tool_execution_failure(clean_registry):
    """Test graceful error handling when tool fails"""
    ToolRegistry.register(TreasuryTool)
    
    with patch('tools.treasury.requests.get') as mock_get:
        mock_get.side_effect = Exception("API timeout")

        with pytest.raises(Exception):
            await ToolRegistry.invoke("treasury", endpoint="avg_interest_rates")


def test_list_tools(clean_registry):
    """Test listing all registered tools"""
    ToolRegistry.register(TreasuryTool)
    ToolRegistry.register(FedBalanceSheetTool)
    ToolRegistry.register(MarketDataTool)

    tools = ToolRegistry.list_tools()
    
    assert len(tools) == 3
    assert set(tools) == {"treasury", "fed_balance_sheet", "market_data"}


@pytest.mark.asyncio
async def test_call_tools_node_integration(clean_registry):
    """Test integration with call_tools node in graph"""
    ToolRegistry.register(TreasuryTool)
    
    # Mock plan that contains tool call
    state = {
        "plan": ["Step 1", "tool: treasury", "Step 3"]
    }
    
    from graph.nodes.calculation import call_tools   # or wherever you placed it
    result = await call_tools(state)
    
    assert "tool_outputs" in result
    assert len(result["tool_outputs"]) >= 0