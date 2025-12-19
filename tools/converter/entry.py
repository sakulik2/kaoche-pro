from core.toolbox.base import ToolMetadata
from .main_tool import ConverterToolPlugin

class ConverterToolEntry(ConverterToolPlugin):
    """
    转换器入口类 - 这里的继承确保了 ToolManager 能够通过 issubclass 发现它
    """
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="converter",
            display_name="字幕格式转换器",
            description="全能型批量字幕转换工具：支持 SRT, ASS, VTT, XLSX, TXT 高效互转",
            icon_path="",
            category="converter"
        )
