from core.toolbox.base import BaseTool
from PyQt6.QtWidgets import QWidget
from .ui.main_view import LqaMainView

class LqaToolPlugin(BaseTool):
    """
    字幕质量分析 (LQA) 工具插件
    """
    def __init__(self, hub):
        super().__init__(hub)
        self.view: LqaMainView = None

    def create_widget(self, parent=None) -> QWidget:
        if not self.view:
            self.view = LqaMainView(self.hub, parent)
        return self.view

    def on_activate(self):
        # 激活时可以执行一些恢复状态的操作
        pass

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
