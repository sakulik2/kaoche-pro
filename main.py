"""
Kaoche Pro - 主应用入口

专业字幕质量分析桌面应用
"""

import sys
import logging
import os
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from ui.main_window import MainWindow
from core.utils.logger import setup_logging

# 确定配置文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'settings.json')

# 初始化日志
setup_logging(CONFIG_PATH)
logger = logging.getLogger(__name__)


def main():
    """应用入口"""
    logger.info("========== kaoche-pro 启动 ==========")
    
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 设置默认字体
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    
    # 设置应用图标
    from PyQt6.QtGui import QIcon
    icon_path = os.path.join(BASE_DIR, 'ui', 'assets', 'icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 创建主窗口
    window = MainWindow()
    
    # i18n 支持
    from PyQt6.QtCore import QTranslator, QLibraryInfo, QLocale
    
    # 1. 加载 Qt 标准翻译 (用于标准对话框按钮等)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    qt_translator = QTranslator(app)
    if qt_translator.load(QLocale.system(), "qtbase", "_", path):
        app.installTranslator(qt_translator)
        
    # 2. 加载应用翻译
    # 读取配置
    lang = "zh_CN" # 默认
    try:
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'settings.json')
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                lang = settings.get('ui', {}).get('language', 'zh_CN')
    except Exception as e:
        logger.error(f"读取语言设置失败: {e}")

    # 对于中文环境，如果没有显式设置为 en_US，则不需要加载翻译文件（因为源码是中文）
    # 但如果用户显式选择了 zh_CN，也不需要加载
    # 只有当语言不是 zh_CN 时才加载对应的 .qm 文件
    
    # 这里我们假设源码是中文 (zh_CN)
    # 如果设置了其他语言，比如 en_US，则加载 kaoche_en_US.qm
    
    if lang != "zh_CN":
        translator = QTranslator(app)
        # 假设翻译文件在 i18n 目录下，命名格式为 kaoche_{lang}.qm
        # 例如: i18n/kaoche_en_US.qm
        qm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n', f'kaoche_{lang}.qm')
        
        # 尝试加载
        if os.path.exists(qm_path):
             if translator.load(qm_path):
                 app.installTranslator(translator)
                 logger.info(f"已加载翻译文件: {qm_path}")
             else:
                 logger.error(f"加载翻译文件失败: {qm_path}")
        else:
             # 尝试模糊匹配，例如 en_US -> en
             lang_short = lang.split('_')[0]
             qm_path_short = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n', f'kaoche_{lang_short}.qm')
             if os.path.exists(qm_path_short):
                 if translator.load(qm_path_short):
                     app.installTranslator(translator)
                     logger.info(f"已加载翻译文件: {qm_path_short}")
                 else:
                     logger.error(f"加载翻译文件失败: {qm_path_short}")
             else:
                 logger.warning(f"未找到翻译文件: {qm_path}")

    window.showMaximized()
    
    logger.info("主窗口已显示")
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
