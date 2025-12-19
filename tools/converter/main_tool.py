from core.toolbox.base import BaseTool
from PyQt6.QtWidgets import QWidget

class ConverterToolPlugin(BaseTool):
    """
    字幕格式转换器 插件
    """
    def __init__(self, hub):
        super().__init__(hub)
        self.view = None

    def create_widget(self, parent=None) -> QWidget:
        from .ui.main_view import ConverterMainView
        if not self.view:
            self.view = ConverterMainView(self.hub, parent)
        return self.view

    def get_settings_widget(self, parent=None) -> QWidget:
        from .ui.settings_panel import ConverterSettingsPanel
        return ConverterSettingsPanel(self.hub, parent)

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass
