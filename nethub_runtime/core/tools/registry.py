"""
Tool Registry - Manages available tools and capabilities.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Callable
from abc import ABC, abstractmethod

LOGGER = logging.getLogger("nethub_runtime.core.tools")


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称
            description: 工具描述
        """
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """
        执行工具
        
        Args:
            input_data: 输入数据
        
        Returns:
            执行结果
        """
        pass
    
    def get_schema(self) -> dict[str, Any]:
        """获取工具schema（用于Agent调用）"""
        return {
            "name": self.name,
            "description": self.description,
            "type": "tool",
        }


class ToolRegistry:
    """
    工具注册表
    
    管理所有可用的工具和能力，支持：
    - 注册/注销工具
    - 按名称查询工具
    - 列出所有工具
    """
    
    def __init__(self):
        """初始化工具注册表"""
        self.tools: dict[str, BaseTool] = {}
        LOGGER.info("✓ Tool Registry initialized")
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tools[tool.name] = tool
        LOGGER.debug(f"  Tool registered: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """
        注销工具
        
        Args:
            name: 工具名称
        """
        if name in self.tools:
            del self.tools[name]
            LOGGER.debug(f"  Tool unregistered: {name}")
        else:
            LOGGER.warning(f"Tool not found: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
        
        Returns:
            工具实例，如果未找到则返回 None
        """
        return self.tools.get(name)
    
    def list_all(self) -> list[str]:
        """
        列出所有工具名称
        
        Returns:
            工具名称列表
        """
        return list(self.tools.keys())
    
    def list_with_schemas(self) -> list[dict[str, Any]]:
        """
        列出所有工具的 schema
        
        Returns:
            工具 schema 列表
        """
        return [tool.get_schema() for tool in self.tools.values()]
    
    async def execute(self, tool_name: str, input_data: dict[str, Any]) -> Any:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            input_data: 输入数据
        
        Returns:
            执行结果
        """
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        try:
            result = await tool.execute(input_data)
            return result
        except Exception as e:
            LOGGER.error(f"Tool execution failed: {tool_name}, error: {e}")
            raise


# ========== 内置工具示例 ==========

class WebSearchTool(BaseTool):
    """Web搜索工具"""
    
    def __init__(self):
        super().__init__("web_search", "Search the web for information")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """执行Web搜索"""
        query = input_data.get("query", "")
        LOGGER.debug(f"Executing web search: {query}")
        
        # TODO: 实现实际的Web搜索
        return {
            "success": True,
            "results": [
                {"title": f"Result for {query}", "url": "https://example.com"}
            ]
        }


class FileSystemTool(BaseTool):
    """文件系统工具"""
    
    def __init__(self):
        super().__init__("filesystem", "Access file system operations")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """执行文件系统操作"""
        operation = input_data.get("operation", "")
        LOGGER.debug(f"Executing filesystem operation: {operation}")
        
        # TODO: 实现实际的文件系统操作
        return {
            "success": True,
            "result": f"Operation {operation} completed"
        }


class ShellExecutionTool(BaseTool):
    """Shell执行工具"""
    
    def __init__(self):
        super().__init__("shell", "Execute shell commands")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """执行Shell命令"""
        command = input_data.get("command", "")
        LOGGER.debug(f"Executing shell command: {command}")
        
        # TODO: 实现实际的Shell命令执行
        return {
            "success": True,
            "output": f"Command executed: {command}"
        }


class CodeExecutionTool(BaseTool):
    """代码执行工具"""
    
    def __init__(self):
        super().__init__("code_execution", "Execute Python code")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """执行Python代码"""
        code = input_data.get("code", "")
        LOGGER.debug(f"Executing code: {code[:50]}...")
        
        # TODO: 实现实际的代码执行
        return {
            "success": True,
            "result": "Code executed"
        }
