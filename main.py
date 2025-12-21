"""
Kaoche Pro - 主应用入口

专业字幕质量分析桌面应用
"""

import sys
import logging
import os
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from ui.launcher.main_window import LauncherWindow
from core.toolbox.manager import ToolManager
from core.toolbox.hub import SharedHub
from core.utils.logger import setup_logging


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'settings.json')
setup_logging(CONFIG_PATH)
logger = logging.getLogger(__name__)

def main():
    """应用入口 - 工具箱版本"""
    logger.info("========== kaoche-pro 工具箱启动 ==========")
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 全局样式抛光：极简 Windows 质感
    app.setStyleSheet("""
        QScrollBar:vertical {
            border: none;
            background: #f1f1f1;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #cdcdcd;
            min-height: 20px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #a6a6a6;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        QScrollBar:horizontal {
            border: none;
            background: #f1f1f1;
            height: 8px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #cdcdcd;
            min-width: 20px;
            border-radius: 4px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }

        /* 统一输入框焦点 */
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border: 1px solid #2563eb;
        }
    """)
    
    # 设置默认字体和图标 (保留原有逻辑)
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    icon_path = os.path.join(BASE_DIR, 'ui', 'assets', 'icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # --- 工具箱初始化核心 ---
    # 1. 初始化共享资源中心
    hub = SharedHub()
    
    # 初始化配置并设置到 hub
    from core.utils.config_manager import get_config_manager
    config_manager = get_config_manager()
    hub.set_config(config_manager)
    
    # 初始化历史管理器 (Folder Memory)
    from core.utils.history_manager import HistoryManager
    hub.history = HistoryManager()
    
    # 2. 初始化工具管理器并扫描插件
    manager = ToolManager(hub)
    tools_dir = os.path.join(BASE_DIR, "tools")
    manager.discover_tools(tools_dir)
    
    # 3. 创建并显示主启动器
    window = LauncherWindow(manager, hub)
    
    # [保留 i18n 逻辑...]
    
    window.show()
    logger.info("工具箱主窗口已显示")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
