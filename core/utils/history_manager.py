import os
from PyQt6.QtCore import QSettings

class HistoryManager:
    """
    负责管理用户的操作历史，如最近访问的目录
    使用 QSettings 存储，跨会话持久化
    """
    def __init__(self, organization="kaoche", application="kaoche-pro"):
        self.settings = QSettings(organization, application)

    def get_last_dir(self, key: str, default: str = "") -> str:
        """获取指定类型的最后访问目录 (subtitle, video, project, etc.)"""
        path = self.settings.value(f"history/last_dir_{key}", default)
        if path and os.path.exists(path):
            return path
        return default

    def set_last_dir(self, key: str, path: str):
        """记录最后访问的目录"""
        if os.path.isfile(path):
            path = os.path.dirname(path)
            
        if os.path.isdir(path):
            self.settings.setValue(f"history/last_dir_{key}", path)
            self.settings.sync()

    def get_recent_files(self, key: str) -> list:
        """[未来扩展] 获取最近文件列表"""
        return self.settings.value(f"history/recent_{key}", [])

    def add_recent_file(self, key: str, file_path: str, max_count: int = 10):
        """[未来扩展] 添加到最近文件列表"""
        files = self.get_recent_files(key)
        if file_path in files:
            files.remove(file_path)
        files.insert(0, file_path)
        self.settings.setValue(f"history/recent_{key}", files[:max_count])
