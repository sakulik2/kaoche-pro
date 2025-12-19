import os
import importlib
import logging
from typing import Dict, List, Type, Optional
from .base import BaseTool

logger = logging.getLogger(__name__)

class ToolManager:
    """
    工具管理器
    负责扫描 tools/ 目录，动态加载插件并管理其实例
    """
    
    def __init__(self, hub):
        self.hub = hub
        self.tools: Dict[str, BaseTool] = {}  # {tool_name: tool_instance}
        self.tool_classes: Dict[str, Type[BaseTool]] = {}
        
    def discover_tools(self, tools_dir: str):
        """
        扫描指定目录下的工具插件
        预期结构: tools/tool_name/entry.py 中定义了插件类
        """
        if not os.path.exists(tools_dir):
            logger.warning(f"工具目录不存在: {tools_dir}")
            return

        for item in os.listdir(tools_dir):
            item_path = os.path.join(tools_dir, item)
            if os.path.isdir(item_path) and not item.startswith('__'):
                self._load_tool_module(item, item_path)

    def _load_tool_module(self, tool_name: str, path: str):
        """动态加载单个工具模块"""
        try:
            # 尝试加载 tools.<tool_name>.entry
            module_path = f"tools.{tool_name}.entry"
            module = importlib.import_module(module_path)
            
            # 寻找继承自 BaseTool 的类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseTool) and 
                    attr is not BaseTool):
                    
                    self.tool_classes[tool_name] = attr
                    logger.info(f"成功发现工具: {tool_name}")
                    return
            
            logger.warning(f"在 {module_path} 中未找到合法的 BaseTool 实现")
        except Exception as e:
            logger.error(f"加载工具 {tool_name} 失败: {str(e)}")

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取或创建工具实例 (单例模式)"""
        if tool_name in self.tools:
            return self.tools[tool_name]
            
        if tool_name in self.tool_classes:
            try:
                instance = self.tool_classes[tool_name](self.hub)
                self.tools[tool_name] = instance
                return instance
            except Exception as e:
                logger.error(f"实例化工具 {tool_name} 失败: {str(e)}")
        
        return None

    def list_available_tools(self) -> List[str]:
        """返回已发现的工具列表"""
        return list(self.tool_classes.keys())
