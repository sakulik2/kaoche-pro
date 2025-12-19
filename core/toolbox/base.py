from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QIcon

class ToolMetadata:
    """工具元数据"""
    def __init__(self, 
                 name: str,
                 display_name: str,
                 description: str,
                 icon_path: str = "",
                 category: str = "General",
                 version: str = "1.0.0"):
        self.name = name
        self.display_name = display_name
        self.description = description
        self.icon_path = icon_path
        self.category = category
        self.version = version

class BaseTool(ABC):
    """
    工具基类 - 所有工具插件必须继承此类
    """
    
    def __init__(self, hub: Any):
        """
        初始化工具
        :param hub: SharedHub 实例，用于访问全局资源
        """
        self.hub = hub
        self.widget: Optional[QWidget] = None

    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """返回工具的展示元数据"""
        pass

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        创建并返回工具的主界面 Widget
        此方法应在工具被选中时调用，支持懒加载
        """
        pass

    def on_activate(self):
        """当用户切换到该工具时触发"""
        pass

    def on_deactivate(self):
        """当用户离开该工具或关闭工具箱时触发"""
        pass

    def get_settings_widget(self, parent: Optional[QWidget] = None) -> Optional[QWidget]:
        """
        [可选] 返回工具专属的设置界面 Widget
        如果返回 None，则该工具没有独立设置项
        """
        return None

    def save_state(self) -> Dict[str, Any]:
        """保存工具当前的工作状态（用于存入项目文件）"""
        return {}

    def restore_state(self, state: Dict[str, Any]):
        """从项目文件中恢复工具状态"""
        pass
