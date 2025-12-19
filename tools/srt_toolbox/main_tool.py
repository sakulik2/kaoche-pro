from core.toolbox.base import BaseTool, ToolMetadata
from PyQt6.QtWidgets import QWidget
from .ui.main_view import SrtToolboxMainView

class SrtToolboxPlugin(BaseTool):
    """
    字幕工具箱插件
    """
    def __init__(self, hub):
        super().__init__(hub)
        self.view = None

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="srt_toolbox",
            display_name="字幕工具箱",
            description="提供字幕合并、智控拆分、内容清洗及时间轴精准偏移等全能操作。",
            category="toolbox",
            icon_path="🛠️" # 暂时使用 Emoji 占位
        )

    def create_widget(self, parent=None) -> QWidget:
        if not self.view:
            self.view = SrtToolboxMainView(self.hub, parent)
        return self.view

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass
