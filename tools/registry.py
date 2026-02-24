# tools/registry.py
"""
Tool Registry

Central registry for all tools. Supports graceful registration with error handling.
"""

from typing import Any, Dict, Type

from observability.logger import log_debug, log_error, log_info, log_warning

from .base import BaseTool

# Import tools with safe handling
tools_to_register = []

try:
    from .bank_capital import BankCapitalTool

    tools_to_register.append(BankCapitalTool)
except ImportError:
    log_warning("BankCapitalTool not found or file is empty. Skipping registration.")

try:
    from .treasury import TreasuryTool

    tools_to_register.append(TreasuryTool)
except ImportError:
    log_warning("TreasuryTool not found. Skipping registration.")

try:
    from .fed_balance_sheet import FedBalanceSheetTool

    tools_to_register.append(FedBalanceSheetTool)
except ImportError:
    log_warning("FedBalanceSheetTool not found. Skipping registration.")

try:
    from .market_data import MarketDataTool

    tools_to_register.append(MarketDataTool)
except ImportError:
    log_warning("MarketDataTool not found. Skipping registration.")


class ToolRegistry:
    _instance = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, tool_class: Type[BaseTool]):
        """Register a tool class safely."""
        try:
            tool = tool_class()
            cls._tools[tool.name] = tool
            log_info(f"Registered tool: {tool.name}")
        except Exception as e:
            log_error(f"Failed to register tool {tool_class.__name__}", error=str(e))

    @classmethod
    def get_tool(cls, name: str) -> BaseTool:
        tool = cls._tools.get(name)
        if not tool:
            log_warning(f"Tool not found: {name}")
            raise ValueError(f"Tool '{name}' not registered")
        return tool

    @classmethod
    def list_tools(cls) -> list:
        tools_list = list(cls._tools.keys())
        log_debug(f"Listed tools: {tools_list}")
        return tools_list

    @classmethod
    async def invoke(cls, name: str, *args, **kwargs) -> Any:
        """Invoke a registered tool asynchronously."""
        tool = cls.get_tool(name)
        log_debug(f"Invoking tool: {name}")

        try:
            result = await tool.aexecute(*args, **kwargs)
            log_info(f"Tool {name} executed successfully")
            return result
        except Exception as e:
            log_error(f"Tool {name} execution failed", error=str(e))
            raise


# Auto-register available tools
for tool_class in tools_to_register:
    ToolRegistry.register(tool_class)

log_info(f"ToolRegistry initialized with {len(ToolRegistry._tools)} tools")
