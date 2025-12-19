import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SharedHub:
    """
    资源共享中心 (SharedHub)
    作为全局单例，管理所有工具共用的服务实例：
    - VLC 播放器
    - AI API 客户端
    - 全局配置
    - 全局状态
    """
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.config = None
        self.history = None
        self.main_window = None  # 指向 Launcher 窗口

    def register_service(self, name: str, service: Any):
        """注册一个共享服务"""
        self.services[name] = service
        logger.info(f"已注册全局服务: {name}")

    def get_service(self, name: str) -> Optional[Any]:
        """获取共享服务"""
        return self.services.get(name)

    def set_config(self, config_manager):
        """设置全局配置管理器"""
        self.config = config_manager

    def broadcast_message(self, message: str, data: Any = None):
        """
        [未来扩展] 提供工具间的简单通信机制
        """
        pass
