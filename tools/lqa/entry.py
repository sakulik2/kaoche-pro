from core.toolbox.base import BaseTool, ToolMetadata
from .main_tool import LqaToolPlugin

class LqaToolEntry(LqaToolPlugin):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="lqa",
            display_name="字幕质量分析",
            description="基于 AI 的专业级字幕质量分析与自动对齐工具",
            icon_path="",
            category="quality"
        )
