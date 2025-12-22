from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFormLayout, QGroupBox,
                             QMessageBox, QScrollArea, QWidget, QTabWidget,
                             QTableWidget, QTableWidgetItem,
                             QComboBox, QSpinBox, QCheckBox, QFrame, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
import json
import os
import logging

logger = logging.getLogger(__name__)

class ProviderManagerDialog(QDialog):
    """
    提供商管理对话框：允许用户编辑 providers.json
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理 AI 提供商")
        self.resize(600, 450)
        from core.api.api_client import load_providers_config, save_providers_config
        self.providers = load_providers_config()
        self.save_func = save_providers_config
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "名称", "已配置模型数"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        self.btn_edit = QPushButton("编辑选中项")
        self.btn_edit.clicked.connect(self.on_edit)
        btn_layout.addWidget(self.btn_edit)
        
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(0)
        for pid, cfg in self.providers.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(pid))
            self.table.setItem(row, 1, QTableWidgetItem(cfg.get('display_name', pid)))
            self.table.setItem(row, 2, QTableWidgetItem(str(len(cfg.get('models', [])))))

    def on_edit(self):
        row = self.table.currentRow()
        if row < 0: return
        pid = self.table.item(row, 0).text()
        cfg = self.providers.get(pid)
        
        from PyQt6.QtWidgets import QInputDialog
        models_str = ",".join(cfg.get('models', []))
        new_models_str, ok = QInputDialog.getText(self, "编辑模型列表", 
                                               f"编辑 {pid} 的模型 (逗号分隔):", 
                                               QLineEdit.EchoMode.Normal, models_str)
        
        if ok and new_models_str:
            # 更新内存
            models = [m.strip() for m in new_models_str.split(',') if m.strip()]
            cfg['models'] = models
            
            # 持续化
            try:
                self.save_func(self.providers)
                self.refresh_table()
                QMessageBox.information(self, "成功", f"提供商 {pid} 的模型列表已更新。")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {e}")

class SettingsDialog(QDialog):
    def __init__(self, hub, parent=None, initial_tab=None):
        super().__init__(parent)
        self.hub = hub
        self.setWindowTitle("kaoche-pro 全局设置")
        self.resize(750, 600)
        self.initial_tab = initial_tab
        self.cm = self.hub.config if self.hub else None
        self.settings = self.cm.load() if self.cm else {}
        from core.api.api_client import load_providers_config
        self.providers_config = load_providers_config()
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setup_ui()
        self.load_values()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #ffffff; }
            QTabWidget::pane {
                border: 1px solid #e5e7eb;
                border-top: none;
                background-color: #ffffff;
            }
            QTabBar::tab {
                padding: 12px 25px;
                color: #4b5563;
                background-color: #f9fafb;
                border: 1px solid #e5e7eb;
                border-bottom: none;
                font-size: 13px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #2563eb;
                border-bottom: 2px solid #2563eb;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected { background-color: #f3f4f6; }
            
            QGroupBox {
                font-weight: 700;
                border: 1px solid #e5e7eb;
                border-radius: 4px;
                margin-top: 25px;
                padding-top: 15px;
                color: #111827;
                font-size: 13px;
            }
            QLabel { color: #374151; font-size: 12px; }
            QLineEdit, QComboBox, QSpinBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px;
                background: white;
                color: #111827;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 0)
        layout.setSpacing(10)
        
        self.tabs = QTabWidget()
        
        # 添加标签页
        self.tabs.addTab(self.create_api_tab(), "AI 接口服务")
        self.tabs.addTab(self.create_ui_tab(), "界面与偏好")
        
        tool_settings = self.get_active_tool_settings()
        if tool_settings:
            # 确保工具设置页有足够的内边距
            container = QWidget()
            cont_layout = QVBoxLayout(container)
            cont_layout.setContentsMargins(20, 10, 20, 10)
            cont_layout.addWidget(tool_settings)
            self.tabs.addTab(container, "当前工具设置")
            
        self.tabs.addTab(self.create_about_tab(), "关于 kaoche-pro")
            
        layout.addWidget(self.tabs)

        # 底部按钮区
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 10, 0, 15)
        footer_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)
        save_btn = QPushButton("保存所有设置")
        save_btn.setFixedSize(120, 32)
        save_btn.setStyleSheet("background-color: #2563eb; color: white; border-radius: 4px; font-weight: 600;")
        save_btn.clicked.connect(self.save_all)
        footer_layout.addWidget(save_btn)
        layout.addWidget(footer)

        if self.initial_tab == "tool" and self.tabs.count() >= 3:
            self.tabs.setCurrentIndex(2)
        else:
            self.tabs.setCurrentIndex(0)

    def on_nav_changed(self, index):
        # 保持兼容性，虽然 QTabWidget 不需要这个信号
        pass

    def add_nav_item(self, text, widget):
        # 保持兼容性
        self.tabs.addTab(widget, text)

    def on_provider_manage(self):
        dialog = ProviderManagerDialog(self)
        dialog.exec()

    def create_api_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 10, 20, 10)
        
        group = QGroupBox("提供商与模型管理")
        form = QFormLayout(group)
        
        provider_row = QHBoxLayout()
        self.provider_combo = QComboBox()
        for pid, cfg in self.providers_config.items():
            self.provider_combo.addItem(cfg.get('display_name', cfg['name']), pid)
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        provider_row.addWidget(self.provider_combo, 1)
        
        btn_manage = QPushButton("管理...")
        btn_manage.clicked.connect(self.on_provider_manage) # 集成管理功能
        provider_row.addWidget(btn_manage)
        form.addRow("AI 提供商:", provider_row)
        
        # 模型选择
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        model_row.addWidget(self.model_combo, 1)
        
        btn_refresh = QPushButton("🔄 刷新列表")
        btn_refresh.clicked.connect(self.refresh_models)
        model_row.addWidget(btn_refresh)
        form.addRow("模型选择:", model_row)
        
        # API Key
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key:", self.key_input)
        
        layout.addWidget(group)
        layout.addStretch()
        return widget

    def create_ui_tab(self):
        widget = QWidget()
        form = QFormLayout(widget)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["霜白 (Vibrant Frost)", "深邃 (Midnight)"]) # 暂未完全实现主题切换，先占位
        form.addRow("界面主题:", self.theme_combo)
        
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 20)
        self.font_size.setValue(10)
        form.addRow("基础字号:", self.font_size)
        
        return widget

    def create_about_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        # Logo
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            icon_label.setPixmap(pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon_label.setText("🚀")
            icon_label.setStyleSheet("font-size: 64px;")
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Title
        title = QLabel("kaoche-pro")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Version
        version = QLabel("Version 1.2.0 (Stable)")
        version.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #e2e8f0; max-width: 300px;")
        layout.addWidget(line, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Description
        desc = QLabel("下一代智能字幕生产力工具\n让 AI 真正深入潜行到字幕工作的每一个细节")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #475569; line-height: 1.6; font-size: 14px;")
        layout.addWidget(desc)
        
        layout.addStretch()
        
        # Footer
        footer = QLabel("© 2025 kaoche-pro Team. All rights reserved.")
        footer.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(footer, 0, Qt.AlignmentFlag.AlignCenter)
        
        return widget

    def get_active_tool_settings(self):
        """尝试获取当前活跃工具的专属设置面板"""
        if self.hub and self.hub.main_window:
            stack = self.hub.main_window.content_stack
            current_widget = stack.currentWidget()
            # 在这种插件架构下，我们需要找到对应的 tool 实例
            for tool in self.hub.main_window.manager.tools.values():
                if tool.widget == current_widget:
                    widget = tool.get_settings_widget(self)
                    if widget:
                        # 统一边距处理
                        widget.setContentsMargins(0, 0, 0, 0)
                    return widget
        return None

    def refresh_models(self):
        provider_id = self.provider_combo.currentData()
        api_key = self.key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "错误", "请先输入 API Key")
            return
        
        try:
            from core.api.api_client import get_models_with_cache, save_providers_config
            config = self.providers_config.get(provider_id)
            models = get_models_with_cache(provider_id, config, api_key)
            
            if models:
                self.model_combo.clear()
                self.model_combo.addItems(models)
                
                # 持久化抓取到的模型列表
                config['models'] = models
                save_providers_config(self.providers_config)
                
                QMessageBox.information(self, f"完成", f"已成功抓取并同步 {len(models)} 个模型")
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", str(e))

    def on_provider_changed(self, index):
        pid = self.provider_combo.currentData()
        cfg = self.providers_config.get(pid, {})
        self.model_combo.clear()
        self.model_combo.addItems(cfg.get('models', []))
        
        # 切换服务商时自动加载对应的 API Key
        # 这样做是为了支持多提供商配置。当用户在下拉列表中选择不同的 AI 服务商时，
        # 界面应自动填充该服务商对应的密钥，从而实现多厂商配置的无缝切换和独立管理。
        if self.cm:
            saved_key = self.cm.get_api_key(self.cm.password, provider_id=pid)
            self.key_input.setText(saved_key or "")

    def load_values(self):
        if not self.settings: return
        
        # 加载 provider
        provider = self.settings.get('api', {}).get('provider', 'openai')
        idx = self.provider_combo.findData(provider)
        if idx >= 0: self.provider_combo.setCurrentIndex(idx)
        
        # 加载 model
        model = self.settings.get('api', {}).get('model', '')
        if model:
            if self.model_combo.findText(model) == -1:
                self.model_combo.addItem(model)
            self.model_combo.setCurrentText(model)
            
        # 加载 Key (通过 CM 获取明文)
        if self.cm:
            self.key_input.setText(self.cm.get_api_key(self.cm.password) or "")

    def save_all(self):
        # 1. 触发工具特定设置的保存
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            # 处理嵌套的 container
            if isinstance(w, QWidget) and w.layout():
                if w.layout().count() > 0:
                    real_w = w.layout().itemAt(0).widget()
                    if hasattr(real_w, 'save_settings'):
                        real_w.save_settings()
            
            if hasattr(w, 'save_settings'):
                try:
                    w.save_settings()
                except Exception as e:
                    logger.error(f"工具设置保存失败: {e}")

        # 2. 更新全局 API settings 字典
        self.settings['api'] = self.settings.get('api', {})
        self.settings['api']['provider'] = self.provider_combo.currentData()
        self.settings['api']['model'] = self.model_combo.currentText()
        
        # 3. 处理 Key 加密保存
        if self.cm:
            self.cm.config = self.settings
            self.cm.set_api_key(self.key_input.text().strip(), self.cm.password)
            self.cm.save(self.settings)
            
        QMessageBox.information(self, "保存成功", "所有设置已持久化。")
        self.accept()
