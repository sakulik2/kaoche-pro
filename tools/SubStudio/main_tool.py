import logging
from core.toolbox.base import BaseTool
from PyQt6.QtWidgets import QWidget
from .ui.main_window import SubStudioMainView

logger = logging.getLogger(__name__)

class SubStudioPlugin(BaseTool):
    """
    SubStudio 专业字幕工作室插件
    """
    def __init__(self, hub):
        super().__init__(hub)
        self.view: SubStudioMainView = None

    def create_widget(self, parent=None) -> QWidget:
        if not self.view:
            self.view = SubStudioMainView(self.hub, parent)
        return self.view

    def on_activate(self):
        # 激活时可能需要刷新配置或检查环境
        pass

    def on_deactivate(self):
        """工具失活或关闭时清理资源"""
        if self.view:
            logger.info("正在停用 SubStudio: 触发视图清理。")
            self.view.close()

    def save_state(self) -> dict:
        """保存工具项目数据 (用于 .kcp)"""
        if self.view:
            return self.view.get_project_data()
        return {}

    def restore_state(self, state: dict):
        """恢复工具项目数据 (从 .kcp)"""
        # 确保 widget 已创建
        self.create_widget()
        if self.view:
            self.view.load_project_data(state)
