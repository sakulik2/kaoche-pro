from core.toolbox.base import BaseTool, ToolMetadata
from .main_tool import SubStudioPlugin

class SubStudioEntry(SubStudioPlugin):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="SubStudio",
            display_name="SubStudio 专业字幕",
            description="专业级 AI 字幕生产工作室 (Professional Subtitle Studio)",
            icon_path="", # TODO: Add icon later
            category="creation" 
        )
