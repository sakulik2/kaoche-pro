import sys
import os
import logging
import json
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QListWidgetItem, QStackedWidget, 
                             QLabel, QPushButton, QFrame, QGridLayout, QScrollArea,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtGui import QIcon, QFont, QColor, QPalette, QLinearGradient, QBrush

logger = logging.getLogger(__name__)

class ToolCard(QFrame):
    """
    点击式工具卡片 - 用于 Dashboard
    """
    def __init__(self, metadata, clicked_callback, parent=None):
        super().__init__(parent)
        self.metadata = metadata
        self.clicked_callback = clicked_callback
        self.setup_ui()

    def setup_ui(self):
        self.setFixedSize(260, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ToolCard")
        
        # 专业、扁平、高密度样式
        self.setStyleSheet("""
            #ToolCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
            }
            #ToolCard:hover {
                border: 1px solid #3b82f6;
                background-color: #f8fafc;
            }
            #ToolTitle {
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
            }
            #ToolDesc {
                font-size: 12px;
                color: #475569;
                line-height: 1.3;
            }
            #CategoryTag {
                background-color: #f1f5f9;
                color: #64748b;
                border: 1px solid #e2e8f0;
                border-radius: 2px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 600;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # 类别标签
        tag_layout = QHBoxLayout()
        self.category_label = QLabel(self.metadata.category)
        self.category_label.setObjectName("CategoryTag")
        tag_layout.addWidget(self.category_label)
        tag_layout.addStretch()
        layout.addLayout(tag_layout)

        # 标题
        self.title_label = QLabel(self.metadata.display_name)
        self.title_label.setObjectName("ToolTitle")
        layout.addWidget(self.title_label)

        # 描述
        self.desc_label = QLabel(self.metadata.description)
        self.desc_label.setObjectName("ToolDesc")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_callback(self.metadata.name)
        super().mousePressEvent(event)

class DashboardView(QWidget):
    """
    专业级的工具选择界面 (首屏)
    """
    def __init__(self, manager, select_callback, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.select_callback = select_callback
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 20)
        layout.setSpacing(15)

        # 头部欢迎
        header_layout = QVBoxLayout()
        title = QLabel("KAOCHE PRO")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: 1px;")
        subtitle = QLabel("专业字幕处理工具箱 | Subtitle Productivity Suite")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # 滚动区域存放网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(container)
        self.grid.setSpacing(20)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # 悬浮设置按钮 (右下角)
        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.setFixedSize(80, 32)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setObjectName("SettingsBtn")
        self.settings_btn.setStyleSheet("""
            #SettingsBtn {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                color: #374151;
            }
            #SettingsBtn:hover {
                background-color: #f9fafb;
                border: 1px solid #9ca3af;
                color: #111827;
            }
        """)
        
        # 放置在右下角
        overlay_layout = QHBoxLayout()
        overlay_layout.addStretch()
        overlay_layout.addWidget(self.settings_btn)
        layout.addLayout(overlay_layout)

        self.settings_btn.clicked.connect(self.on_settings_clicked)

        self.load_cards()

    def on_settings_clicked(self):
        from ui.shared.settings_dialog import SettingsDialog
        hub = getattr(self.window(), 'hub', None)
        dialog = SettingsDialog(hub, self)
        dialog.exec()

    def load_cards(self):
        tool_names = self.manager.list_available_tools()
        cols = 3
        for i, name in enumerate(tool_names):
            tool = self.manager.get_tool(name)
            if tool:
                card = ToolCard(tool.get_metadata(), self.select_callback)
                self.grid.addWidget(card, i // cols, i % cols)

class LauncherWindow(QMainWindow):
    """
    工具箱主窗口 - 整合 Dashboard 和 工具视图
    """
    def __init__(self, manager, hub):
        super().__init__()
        self.manager = manager
        self.hub = hub
        self.hub.main_window = self
        
        self.setWindowTitle("kaoche-pro")
        self.setMinimumSize(1100, 800)
        self.resize(1200, 850)
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 专业背景：浅灰中性色，无渐变
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f3f4f6;
            }
        """)
        
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 顶部 Header (默认隐藏)
        self.header = QFrame()
        self.header.setFixedHeight(40)
        self.header.setVisible(False)
        self.header.setObjectName("Header")
        self.header.setStyleSheet("""
            #Header {
                background-color: #ffffff;
                border-bottom: 1px solid #d1d5db;
            }
            QLabel#ToolTitle {
                font-family: 'Segoe UI', 'Microsoft YaHei UI';
                font-weight: 700;
                font-size: 14px;
                color: #111827;
            }
            QPushButton#HeaderBtn {
                background: transparent;
                color: #4b5563;
                padding: 4px 12px;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#HeaderBtn:hover {
                background-color: #f3f4f6;
                border: 1px solid #d1d5db;
                color: #111827;
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        # 左侧：返回
        self.back_btn = QPushButton("← 仪表盘")
        self.back_btn.setObjectName("HeaderBtn")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.show_dashboard)
        header_layout.addWidget(self.back_btn)

        header_layout.addStretch()

        # 中间偏左：项目操作 (默认隐藏)
        self.project_ops = QWidget()
        self.project_ops.setVisible(False)
        project_layout = QHBoxLayout(self.project_ops)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.setSpacing(5)
        
        self.btn_open_proj = QPushButton("📂 打开项目")
        self.btn_open_proj.setObjectName("HeaderBtn")
        self.btn_open_proj.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_proj.clicked.connect(self.on_open_project)
        project_layout.addWidget(self.btn_open_proj)
        
        self.btn_save_proj = QPushButton("💾 保存项目")
        self.btn_save_proj.setObjectName("HeaderBtn")
        self.btn_save_proj.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_proj.clicked.connect(self.on_save_project)
        project_layout.addWidget(self.btn_save_proj)
        
        header_layout.addWidget(self.project_ops)

        # 中间：标题
        self.current_tool_label = QLabel("工具名称")
        self.current_tool_label.setObjectName("ToolTitle")
        header_layout.addWidget(self.current_tool_label)

        header_layout.addStretch()

        # 右侧：设置
        self.global_settings_btn = QPushButton("⚙️ 功能配置")
        self.global_settings_btn.setObjectName("HeaderBtn")
        self.global_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.global_settings_btn.clicked.connect(lambda: self.on_settings_clicked(initial_tab="tool"))
        header_layout.addWidget(self.global_settings_btn)

        # 2. 内容堆栈
        self.content_stack = QStackedWidget()
        
        # 创建 Dashboard
        self.dashboard = DashboardView(self.manager, self.select_tool_from_dashboard)
        self.content_stack.addWidget(self.dashboard)

        # 组合入主布局
        self.main_layout.addWidget(self.header)
        self.main_layout.addWidget(self.content_stack)

    def select_tool_from_dashboard(self, tool_name):
        """从 Dashboard 点击卡片后的跳转逻辑"""
        self.switch_to_tool(tool_name)

    def switch_to_tool(self, tool_name):
        tool = self.manager.get_tool(tool_name)
        if tool:
            # 确保 widget 已创建
            if not tool.widget:
                tool.widget = tool.create_widget(self.content_stack)
                self.content_stack.addWidget(tool.widget)
            
            # 显示 Header
            self.header.setVisible(True)
            self.project_ops.setVisible(True) # 工具状态下显示项目操作
            meta = tool.get_metadata()
            self.current_tool_label.setText(f"{meta.display_name}")
            
            # 切换 stack
            self.content_stack.setCurrentWidget(tool.widget)
            tool.on_activate()
        else:
            logger.error(f"无法找到工具: {tool_name}")

    def show_dashboard(self):
        self.header.setVisible(False)
        self.content_stack.setCurrentWidget(self.dashboard)

    def on_settings_clicked(self, initial_tab=None):
        from ui.shared.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.hub, self, initial_tab=initial_tab)
        dialog.exec()

    def on_save_project(self):
        """保存当前项目状态"""
        # 1. 寻找当前活跃工具
        current_widget = self.content_stack.currentWidget()
        active_tool = None
        for name, tool in self.manager.tools.items():
            if tool.widget == current_widget:
                active_tool = tool
                break
        
        if not active_tool:
            QMessageBox.warning(self, "提示", "没有活跃的工具可以保存")
            return
            
        # 2. 获取状态
        state = active_tool.save_state()
        if not state:
            QMessageBox.warning(self, "提示", "该工具当前没有可保存的项目数据")
            return
            
        # 3. 选择路径
        last_dir = self.hub.history.get_last_dir("project") if self.hub and self.hub.history else ""
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", last_dir, "Kaoche Project (*.kcp)")
        if not path: return
        
        if self.hub and self.hub.history:
            self.hub.history.set_last_dir("project", path)
            
        # 4. 写入 JSON
        project_data = {
            "version": "1.0",
            "active_tool": active_tool.get_metadata().name,
            "tool_state": state
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "完成", "项目已成功保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def on_open_project(self):
        """打开并恢复项目状态"""
        last_dir = self.hub.history.get_last_dir("project") if self.hub and self.hub.history else ""
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", last_dir, "Kaoche Project (*.kcp)")
        if not path: return
        
        if self.hub and self.hub.history:
            self.hub.history.set_last_dir("project", path)
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            tool_name = data.get("active_tool")
            state = data.get("tool_state")
            
            if not tool_name or state is None:
                raise ValueError("项目文件格式无效")
                
            # 切换工具并恢复
            self.switch_to_tool(tool_name)
            tool = self.manager.get_tool(tool_name)
            if tool:
                tool.restore_state(state)
                QMessageBox.information(self, "完成", "项目已成功加载")
            
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))

    def create_new_instance(self, tool_name=None):
        """创建一个全新的 Launcher 实例（用于多窗口支持）"""
        from main import BASE_DIR
        from core.toolbox.manager import ToolManager
        from core.toolbox.hub import SharedHub
        
        new_hub = SharedHub()
        new_manager = ToolManager(new_hub)
        new_manager.discover_tools(os.path.join(BASE_DIR, "tools"))
        
        new_window = LauncherWindow(new_manager, new_hub)
        new_window.show()
        
        if tool_name:
            new_window.select_tool_from_dashboard(tool_name)
        
        return new_window

    def closeEvent(self, event):
        for tool in self.manager.tools.values():
            tool.on_deactivate()
        super().closeEvent(event)
