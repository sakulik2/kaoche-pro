"""
设置对话框

提供API配置、Prompt管理、界面设置等功能
"""

from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QListWidget,
    QGroupBox, QSpinBox, QCheckBox, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt
import json
import os
import logging

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("设置"))
        self.setModal(True)
        self.resize(700, 600)
        
        # 加载当前设置
        self.settings = self.load_settings()
        self.providers_config = self.load_providers()
        
        self.setup_ui()
        self.load_values()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 标签页
        tabs = QTabWidget()
        tabs.addTab(self.create_api_tab(), self.tr("🔌 LLM配置"))
        tabs.addTab(self.create_prompt_tab(), self.tr("📝 Prompt管理"))
        tabs.addTab(self.create_ui_tab(), self.tr("🎨 界面设置"))
        tabs.addTab(self.create_advanced_tab(), self.tr("⚙️ 高级选项"))
        
        layout.addWidget(tabs)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_save = QPushButton(self.tr("💾 保存"))
        btn_save.clicked.connect(self.save_all_settings)
        button_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton(self.tr("❌ 取消"))
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def create_api_tab(self):
        """API配置标签页"""
        widget = QGroupBox()
        layout = QVBoxLayout(widget)
        
        # 提供商选择
        provider_group = QGroupBox(self.tr("提供商"))
        provider_layout = QVBoxLayout()
        
        # 提供商下拉框和管理按钮
        provider_select_layout = QHBoxLayout()
        self.provider_combo = QComboBox()
        for provider_id, config in self.providers_config.items():
            display_name = config.get('display_name', config['name'])
            self.provider_combo.addItem(display_name, provider_id)
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        provider_select_layout.addWidget(QLabel(self.tr("提供商:")))
        provider_select_layout.addWidget(self.provider_combo, 1)
        
        # 自定义提供商管理按钮
        btn_add_custom = QPushButton("➕")
        btn_add_custom.setToolTip(self.tr("添加自定义提供商"))
        btn_add_custom.setMaximumWidth(35)
        btn_add_custom.clicked.connect(self.add_custom_provider)
        provider_select_layout.addWidget(btn_add_custom)
        
        btn_edit_custom = QPushButton("✏️")
        btn_edit_custom.setToolTip(self.tr("编辑自定义提供商"))
        btn_edit_custom.setMaximumWidth(35)
        btn_edit_custom.clicked.connect(self.edit_custom_provider)
        provider_select_layout.addWidget(btn_edit_custom)
        
        btn_delete_custom = QPushButton("🗑️")
        btn_delete_custom.setToolTip(self.tr("删除自定义提供商"))
        btn_delete_custom.setMaximumWidth(35)
        btn_delete_custom.clicked.connect(self.delete_custom_provider)
        provider_select_layout.addWidget(btn_delete_custom)
        
        provider_layout.addLayout(provider_select_layout)
        
        # 模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel(self.tr("模型:")))
        
        self.model_combo = QComboBox()
        model_layout.addWidget(self.model_combo, 1)
        
        btn_refresh = QPushButton("🔄")
        btn_refresh.setToolTip(self.tr("刷新模型列表"))
        btn_refresh.setMaximumWidth(40)
        btn_refresh.clicked.connect(self.refresh_models)
        model_layout.addWidget(btn_refresh)
        
        provider_layout.addLayout(model_layout)
        
        # API Key - 添加可见性切换按钮
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel(self.tr("API Key:")))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText(self.tr("输入API密钥..."))
        key_layout.addWidget(self.api_key_input, 1)
        
        # 查看/隐藏按钮
        self.btn_toggle_key_visibility = QPushButton("👁️")
        self.btn_toggle_key_visibility.setToolTip(self.tr("显示/隐藏API Key"))
        self.btn_toggle_key_visibility.setMaximumWidth(40)
        self.btn_toggle_key_visibility.setCheckable(True)
        self.btn_toggle_key_visibility.clicked.connect(self.toggle_key_visibility)
        key_layout.addWidget(self.btn_toggle_key_visibility)
        
        provider_layout.addLayout(key_layout)
        
        # 测试按钮
        btn_test = QPushButton(self.tr("🧪 测试连接"))
        btn_test.clicked.connect(self.test_api_connection)
        provider_layout.addWidget(btn_test)
        
        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)
        
        # 性能设置 - 批处理建议
        perf_group = QGroupBox(self.tr("LLM 批处理设置"))
        perf_layout = QFormLayout()
        
        self.batch_size_alignment_spin = QSpinBox()
        self.batch_size_alignment_spin.setRange(1, 100)
        self.batch_size_alignment_spin.setValue(10)
        perf_layout.addRow(self.tr("对齐批处理大小:"), self.batch_size_alignment_spin)
        
        self.batch_size_lqa_spin = QSpinBox()
        self.batch_size_lqa_spin.setRange(1, 100)
        self.batch_size_lqa_spin.setValue(5)
        perf_layout.addRow(self.tr("LQA 批处理大小:"), self.batch_size_lqa_spin)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        layout.addStretch()
        
        return widget
    
    def toggle_key_visibility(self):
        """切换API Key可见性"""
        if self.btn_toggle_key_visibility.isChecked():
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key_visibility.setText("🙈")  # 眼睛遮住图标
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key_visibility.setText("👁️")  # 眼睛图标
    
    def add_custom_provider(self):
        """添加自定义提供商"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("添加自定义提供商"))
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        # 输入字段
        name_input = QLineEdit()
        name_input.setPlaceholderText(self.tr("例如: My API"))
        form.addRow(self.tr("显示名称:"), name_input)
        
        id_input = QLineEdit()
        id_input.setPlaceholderText(self.tr("例如: my_api (唯一标识)"))
        form.addRow("ID:", id_input)
        
        endpoint_input = QLineEdit()
        endpoint_input.setPlaceholderText(self.tr("例如: https://api.example.com/v1"))
        form.addRow(self.tr("API端点:"), endpoint_input)
        
        models_input = QLineEdit()
        models_input.setPlaceholderText(self.tr("例如: gpt-4,gpt-3.5-turbo (逗号分隔)"))
        form.addRow(self.tr("模型列表:"), models_input)
        
        default_model_input = QLineEdit()
        default_model_input.setPlaceholderText(self.tr("例如: gpt-4"))
        form.addRow(self.tr("默认模型:"), default_model_input)
        
        layout.addLayout(form)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            provider_id = id_input.text().strip()
            name = name_input.text().strip()
            endpoint = endpoint_input.text().strip()
            models_str = models_input.text().strip()
            default_model = default_model_input.text().strip()
            
            # 验证
            if not all([provider_id, name, endpoint]):
                QMessageBox.warning(self, self.tr("错误"), self.tr("ID、名称和API端点不能为空"))
                return
            
            if provider_id in self.providers_config:
                QMessageBox.warning(self, self.tr("错误"), self.tr("ID '{}' 已存在").format(provider_id))
                return
            
            # 解析模型列表
            models = [m.strip() for m in models_str.split(',') if m.strip()]
            if not models:
                models = ["gpt-4", "gpt-3.5-turbo"]  # 默认
            
            if not default_model:
                default_model = models[0]
            
            # 添加到配置
            new_provider = {
                "id": provider_id,
                "name": name,
                "display_name": name,
                "api_base": endpoint,
                "api_type": "openai",
                "models": models,
                "default_model": default_model,
                "custom": True
            }
            
            self.providers_config[provider_id] = new_provider
            self._save_providers_config()
            
            # 更新下拉列表
            self.provider_combo.addItem(name, provider_id)
            self.provider_combo.setCurrentText(name)
            
            QMessageBox.information(self, self.tr("成功"), self.tr("自定义提供商 '{}' 已添加").format(name))
    
    def edit_custom_provider(self):
        """编辑自定义提供商"""
        provider_id = self.provider_combo.currentData()
        if not provider_id:
            return
        
        provider = self.providers_config.get(provider_id)
        if not provider:
            return
        
        # 只允许编辑自定义提供商
        if not provider.get('custom', False):
            QMessageBox.information(self, self.tr("提示"), self.tr("只能编辑自定义提供商"))
            return
        
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("编辑自定义提供商"))
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        # 填充现有值
        name_input = QLineEdit()
        name_input.setText(provider.get('display_name', provider['name']))
        form.addRow(self.tr("显示名称:"), name_input)
        
        endpoint_input = QLineEdit()
        endpoint_input.setText(provider['api_base'])
        form.addRow(self.tr("API端点:"), endpoint_input)
        
        models_input = QLineEdit()
        models_input.setText(','.join(provider.get('models', [])))
        form.addRow(self.tr("模型列表:"), models_input)
        
        default_model_input = QLineEdit()
        default_model_input.setText(provider.get('default_model', ''))
        form.addRow(self.tr("默认模型:"), default_model_input)
        
        layout.addLayout(form)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            endpoint = endpoint_input.text().strip()
            models_str = models_input.text().strip()
            default_model = default_model_input.text().strip()
            
            if not all([name, endpoint]):
                QMessageBox.warning(self, self.tr("错误"), self.tr("名称和API端点不能为空"))
                return
            
            # 更新配置
            models = [m.strip() for m in models_str.split(',') if m.strip()]
            
            provider['display_name'] = name
            provider['name'] = name
            provider['api_base'] = endpoint
            provider['models'] = models
            provider['default_model'] = default_model
            
            self._save_providers_config()
            
            # 更新下拉列表
            index = self.provider_combo.currentIndex()
            self.provider_combo.setItemText(index, name)
            
            QMessageBox.information(self, self.tr("成功"), self.tr("提供商已更新"))
    
    def delete_custom_provider(self):
        """删除自定义提供商"""
        provider_id = self.provider_combo.currentData()
        if not provider_id:
            return
        
        provider = self.providers_config.get(provider_id)
        if not provider:
            return
        
        # 只允许删除自定义提供商
        if not provider.get('custom', False):
            QMessageBox.information(self, self.tr("提示"), self.tr("只能删除自定义提供商"))
            return
        
        reply = QMessageBox.question(
            self,
            self.tr("确认"),
            self.tr("确定要删除自定义提供商 '{}' 吗？").format(provider['name']),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 从配置中删除
            del self.providers_config[provider_id]
            self._save_providers_config()
            
            # 从下拉列表删除
            index = self.provider_combo.currentIndex()
            self.provider_combo.removeItem(index)
            
            QMessageBox.information(self, self.tr("成功"), self.tr("自定义提供商已删除"))
    
    def _save_providers_config(self):
        """保存提供商配置"""
        try:
            from core.utils.utils import get_project_root
            root = get_project_root()
            providers_file = os.path.join(root, 'config', 'providers.json')
            
            # 转换为providers数组格式
            providers_list = list(self.providers_config.values())
            
            with open(providers_file, 'w', encoding='utf-8') as f:
                json.dump({'providers': providers_list}, f, indent=2, ensure_ascii=False)
            
            logger.info("提供商配置已保存")
            
        except Exception as e:
            logger.error(f"保存提供商配置失败: {e}")
    
    def create_prompt_tab(self):
        """Prompt管理标签页"""
        widget = QGroupBox()
        layout = QVBoxLayout(widget)
        
        # Prompt预设列表
        list_group = QGroupBox(self.tr("Prompt预设"))
        list_layout = QVBoxLayout()
        
        self.prompt_list = QListWidget()
        self.load_prompt_list()
        self.prompt_list.currentRowChanged.connect(self.on_prompt_selected)
        list_layout.addWidget(self.prompt_list)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_new = QPushButton(self.tr("➕ 新建"))
        btn_new.clicked.connect(self.new_prompt)
        btn_layout.addWidget(btn_new)
        
        btn_edit = QPushButton(self.tr("✏️ 编辑"))
        btn_edit.clicked.connect(self.edit_prompt)
        btn_layout.addWidget(btn_edit)
        
        btn_delete = QPushButton(self.tr("🗑️ 删除"))
        btn_delete.clicked.connect(self.delete_prompt)
        btn_layout.addWidget(btn_delete)
        
        btn_import = QPushButton(self.tr("📂 导入"))
        btn_import.clicked.connect(self.import_prompt)
        btn_layout.addWidget(btn_import)
        
        list_layout.addLayout(btn_layout)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # Prompt预览
        preview_group = QGroupBox(self.tr("预览"))
        preview_layout = QVBoxLayout()
        
        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMaximumHeight(200)
        preview_layout.addWidget(self.prompt_preview)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        return widget
    
    def create_ui_tab(self):
        """界面设置标签页"""
        widget = QGroupBox()
        layout = QFormLayout(widget)
        
        # 语言
        self.language_combo = QComboBox()
        self.language_combo.addItem(self.tr("中文"), "zh_CN")
        
        # 动态检测英文翻译文件
        import os
        from core.utils.utils import get_project_root
        
        i18n_path = os.path.join(get_project_root(), 'i18n', 'kaoche_en.qm')
        if os.path.exists(i18n_path):
            self.language_combo.addItem("English", "en_US")
        layout.addRow(self.tr("语言:"), self.language_combo)
        
        # 字体大小
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        layout.addRow(self.tr("字体大小:"), self.font_size_spin)
        
        # 主题
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.tr("浅色"), "light")
        self.theme_combo.addItem(self.tr("深色"), "dark")
        layout.addRow(self.tr("主题:"), self.theme_combo)
        
        return widget
    
    def create_lqa_tab(self):
        """LQA设置标签页"""
        widget = QGroupBox()
        layout = QFormLayout(widget)
        
        # 目标语言
        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItem(self.tr("中文"), "zh_CN")
        self.target_lang_combo.addItem("English", "en_US")
        self.target_lang_combo.addItem("Japanese", "ja_JP")
        self.target_lang_combo.addItem("Korean", "ko_KR")
        
        layout.addRow(self.tr("目标语言:"), self.target_lang_combo)
        
        return widget
    
    def create_advanced_tab(self):
        """高级选项标签页"""
        widget = QGroupBox()
        layout = QVBoxLayout(widget)
        
        # ===== 语言设置 =====
        lang_group = QGroupBox(self.tr("翻译/检查目标语言"))
        lang_layout = QFormLayout()
        
        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItem(self.tr("中文"), "zh_CN")
        self.target_lang_combo.addItem("English", "en_US")
        self.target_lang_combo.addItem("Japanese", "ja_JP")
        self.target_lang_combo.addItem("Korean", "ko_KR")
        lang_layout.addRow(self.tr("目标语言:"), self.target_lang_combo)
        
        lang_group.setLayout(lang_layout)
        layout.addWidget(lang_group)

        # ===== 性能设置 =====
        perf_group = QGroupBox(self.tr("通用性能设置"))
        perf_layout = QFormLayout()
        
        # 超时设置
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(self.tr(" 秒"))
        perf_layout.addRow(self.tr("API超时:"), self.timeout_spin)
        
        # 缓存TTL
        self.cache_ttl_spin = QSpinBox()
        self.cache_ttl_spin.setRange(300, 86400)
        self.cache_ttl_spin.setValue(3600)
        self.cache_ttl_spin.setSuffix(self.tr(" 秒"))
        perf_layout.addRow(self.tr("缓存有效期:"), self.cache_ttl_spin)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        # ===== 加密设置 =====
        enc_group = QGroupBox(self.tr("🔐 配置加密"))
        enc_layout = QVBoxLayout()
        
        # 说明
        enc_info = QLabel(self.tr("启用加密后，API密钥将使用密码加密保存"))
        enc_info.setStyleSheet("color: gray; font-size: 10px;")
        enc_layout.addWidget(enc_info)
        
        # 加密状态
        self.encryption_checkbox = QCheckBox(self.tr("启用配置加密"))
        self.encryption_checkbox.stateChanged.connect(self.on_encryption_changed)
        enc_layout.addWidget(self.encryption_checkbox)
        
        # 密码输入
        password_layout = QFormLayout()
        self.encryption_password = QLineEdit()
        self.encryption_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.encryption_password.setPlaceholderText(self.tr("设置主密码..."))
        self.encryption_password.setEnabled(False)
        password_layout.addRow(self.tr("主密码:"), self.encryption_password)
        enc_layout.addLayout(password_layout)
        
        # 应用按钮
        enc_btn_layout = QHBoxLayout()
        
        self.btn_enable_encryption = QPushButton(self.tr("✅ 启用加密"))
        self.btn_enable_encryption.clicked.connect(self.enable_encryption)
        self.btn_enable_encryption.setEnabled(False)
        enc_btn_layout.addWidget(self.btn_enable_encryption)
        
        self.btn_disable_encryption = QPushButton(self.tr("❌ 禁用加密"))
        self.btn_disable_encryption.clicked.connect(self.disable_encryption)
        self.btn_disable_encryption.setEnabled(False)
        enc_btn_layout.addWidget(self.btn_disable_encryption)
        
        enc_btn_layout.addStretch()
        enc_layout.addLayout(enc_btn_layout)
        
        enc_group.setLayout(enc_layout)
        layout.addWidget(enc_group)
        
        # ===== VLC设置 =====
        vlc_group = QGroupBox(self.tr("视频播放器设置"))
        vlc_layout = QVBoxLayout()
        
        vlc_path_layout = QHBoxLayout()
        vlc_path_layout.addWidget(QLabel(self.tr("VLC路径:")))
        
        self.vlc_path_input = QLineEdit()
        self.vlc_path_input.setPlaceholderText(self.tr("选择VLC安装目录 (包含libvlc.dll)"))
        vlc_path_layout.addWidget(self.vlc_path_input)
        
        btn_browse_vlc = QPushButton("📂")
        btn_browse_vlc.setMaximumWidth(40)
        btn_browse_vlc.clicked.connect(self.browse_vlc_path)
        vlc_path_layout.addWidget(btn_browse_vlc)
        
        vlc_layout.addLayout(vlc_path_layout)
        
        vlc_info = QLabel(self.tr("提示: 如果自动检测失败，请手动指定VLC安装目录"))
        vlc_info.setStyleSheet("color: gray; font-size: 10px;")
        vlc_layout.addWidget(vlc_info)
        
        vlc_group.setLayout(vlc_layout)
        layout.addWidget(vlc_group)

        # ===== 日志设置 =====
        log_group = QGroupBox(self.tr("日志设置"))
        log_layout = QFormLayout()
        
        # 日志级别
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        log_layout.addRow(self.tr("日志级别:"), self.log_level_combo)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        return widget
    
    def browse_vlc_path(self):
        """选择VLC路径"""
        path = QFileDialog.getExistingDirectory(self, self.tr("选择VLC安装目录"))
        if path:
            self.vlc_path_input.setText(path)
    
    def on_encryption_changed(self, state):
        """加密复选框状态变化"""
        enabled = (state == 2)  # Qt.CheckState.Checked
        self.encryption_password.setEnabled(enabled)
        
        if enabled:
            # 检查当前是否已启用加密
            if self.settings.get('encryption', {}).get('enabled', False):
                self.btn_disable_encryption.setEnabled(True)
                self.btn_enable_encryption.setEnabled(False)
            else:
                self.btn_enable_encryption.setEnabled(True)
                self.btn_disable_encryption.setEnabled(False)
        else:
            self.btn_enable_encryption.setEnabled(False)
            self.btn_disable_encryption.setEnabled(False)
    
    def enable_encryption(self):
        """启用加密"""
        password = self.encryption_password.text().strip()
        
        if not password:
            QMessageBox.warning(self, self.tr("错误"), self.tr("请输入主密码"))
            return
        
        if len(password) < 6:
            QMessageBox.warning(self, self.tr("错误"), self.tr("密码至少需要6个字符"))
            return
        
        try:
            from core.utils.config_manager import ConfigManager
            
            config_manager = ConfigManager()
            config_manager.config = self.settings
            
            if config_manager.enable_encryption(password):
                self.settings = config_manager.config
                QMessageBox.information(self, self.tr("成功"), self.tr("加密已启用！\n\nAPI密钥已加密保存。"))
                
                # 更新UI
                self.btn_enable_encryption.setEnabled(False)
                self.btn_disable_encryption.setEnabled(True)
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("启用加密失败"))
                
        except Exception as e:
            QMessageBox.warning(self, self.tr("错误"), self.tr("启用加密失败: {}").format(str(e)))
    
    def disable_encryption(self):
        """禁用加密"""
        password = self.encryption_password.text().strip()
        
        if not password:
            QMessageBox.warning(self, self.tr("错误"), self.tr("请输入主密码以解密数据"))
            return
        
        reply = QMessageBox.question(
            self,
            self.tr("确认"),
            self.tr("禁用加密后，API密钥将以明文保存。\n\n确定要继续吗？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            from core.utils.config_manager import ConfigManager
            
            config_manager = ConfigManager()
            config_manager.config = self.settings
            config_manager.encryption_enabled = True
            
            if config_manager.disable_encryption(password):
                self.settings = config_manager.config
                QMessageBox.information(self, self.tr("成功"), self.tr("加密已禁用。\n\nAPI密钥已解密为明文。"))
                
                # 更新UI
                self.btn_enable_encryption.setEnabled(True)
                self.btn_disable_encryption.setEnabled(False)
                self.encryption_checkbox.setChecked(False)
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("禁用加密失败（密码可能错误）"))
                
        except Exception as e:
            QMessageBox.warning(self, self.tr("错误"), self.tr("禁用加密失败: {}").format(str(e)))
    
    def load_settings(self):
        """加载设置"""
        from core.utils.config_manager import get_config_manager
        return get_config_manager().load()
    
    def load_providers(self):
        """加载提供商配置"""
        from core.api.api_client import load_providers_config
        return load_providers_config()
    
    def load_values(self):
        """加载当前值到UI"""
        # API配置
        provider = self.settings.get('api', {}).get('provider', 'openai')
        saved_model = self.settings.get('api', {}).get('model', '')  # 先获取保存的模型
        
        index = self.provider_combo.findData(provider)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
            # 手动触发提供商变更以加载模型列表
            self.on_provider_changed(index)
            
            # 提供商变更完成后，恢复保存的模型选择
            if saved_model:
                model_index = self.model_combo.findText(saved_model)
                if model_index >= 0:
                    # 模型在列表中，直接选中
                    self.model_combo.setCurrentIndex(model_index)
                else:
                    # 模型不在列表中（可能是自定义模型），添加并选中
                    self.model_combo.insertItem(0, saved_model)
                    self.model_combo.setCurrentIndex(0)
        
        from core.utils.config_manager import get_config_manager
        cm = get_config_manager()
        api_key = cm.get_api_key(cm.password)
        self.api_key_input.setText(api_key if api_key else self.settings.get('api', {}).get('api_key', ''))
        
        # UI设置
        lang_index = self.language_combo.findData(self.settings.get('ui', {}).get('language', 'zh_CN'))
        if lang_index >= 0:
            self.language_combo.setCurrentIndex(lang_index)
        
        self.font_size_spin.setValue(self.settings.get('ui', {}).get('font_size', 12))
        
        theme_index = self.theme_combo.findData(self.settings.get('ui', {}).get('theme', 'light'))
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
            
        # 从 API 配置中读取批处理大小
        self.batch_size_alignment_spin.setValue(self.settings.get('api', {}).get('batch_size_alignment', 10))
        self.batch_size_lqa_spin.setValue(self.settings.get('api', {}).get('batch_size_lqa', 5))
        
        # 目标语言 (现已在高级选项中)
        target_lang = self.settings.get('ui', {}).get('target_language', 'zh_CN')
        lang_idx = self.target_lang_combo.findData(target_lang)
        if lang_idx >= 0:
            self.target_lang_combo.setCurrentIndex(lang_idx)
        else:
             self.target_lang_combo.addItem(target_lang, target_lang)
             self.target_lang_combo.setCurrentIndex(self.target_lang_combo.count() - 1)
        
        # 高级选项
        self.timeout_spin.setValue(self.settings.get('advanced', {}).get('timeout', 30))
        self.cache_ttl_spin.setValue(self.settings.get('advanced', {}).get('cache_ttl', 3600))
        self.vlc_path_input.setText(self.settings.get('advanced', {}).get('vlc_path', ''))
        
        log_index = self.log_level_combo.findText(self.settings.get('advanced', {}).get('log_level', 'INFO'))
        if log_index >= 0:
            self.log_level_combo.setCurrentIndex(log_index)
        
        # 加密设置
        encryption_enabled = self.settings.get('encryption', {}).get('enabled', False)
        self.encryption_checkbox.setChecked(encryption_enabled)
        if encryption_enabled:
            self.btn_disable_encryption.setEnabled(False)  # 需要密码才能禁用
            self.btn_enable_encryption.setEnabled(False)
    
    def on_provider_changed(self, index):
        """提供商切换 - 保存当前提供商的key/model，加载新提供商的key/model"""
        # 保存当前提供商的设置（如果有）
        current_provider = self.settings.get('api', {}).get('provider')
        if current_provider and hasattr(self, 'api_key_input'):
            # 保存到providers字典
            if 'providers' not in self.settings:
                self.settings['providers'] = {}
            
            self.settings['providers'][current_provider] = {
                'api_key': self.api_key_input.text().strip(),
                'model': self.model_combo.currentText()
            }
        
        # 获取新选择的提供商
        provider_id = self.provider_combo.currentData()
        if not provider_id:
            return
        
        # 更新当前提供商
        if 'api' not in self.settings:
            self.settings['api'] = {}
        self.settings['api']['provider'] = provider_id
        
        provider_config = self.providers_config.get(provider_id)
        if provider_config:
            # 加载模型列表
            models = provider_config.get('models', [])
            self.model_combo.clear()
            self.model_combo.addItems(models)
            
            # 加载该提供商保存的API Key和模型
            provider_settings = self.settings.get('providers', {}).get(provider_id, {})
            
            # 加载API Key
            saved_key = provider_settings.get('api_key', '')
            self.api_key_input.setText(saved_key)
            
            # 加载模型
            saved_model = provider_settings.get('model', '')
            if saved_model:
                model_index = self.model_combo.findText(saved_model)
                if model_index >= 0:
                    self.model_combo.setCurrentIndex(model_index)
                else:
                    # 模型不在列表中，添加并选中
                    self.model_combo.insertItem(0, saved_model)
                    self.model_combo.setCurrentIndex(0)
            else:
                # 没有保存的模型，使用默认模型
                default_model = provider_config.get('default_model')
                if default_model:
                    default_index = self.model_combo.findText(default_model)
                    if default_index >= 0:
                        self.model_combo.setCurrentIndex(default_index)
    
    def refresh_models(self):
        """刷新模型列表"""
        provider_id = self.provider_combo.currentData()
        api_key = self.api_key_input.text().strip()
        
        if not api_key:
            QMessageBox.warning(self, "提示", "请先输入API密钥")
            return
        
        try:
            from core.api.api_client import get_models_with_cache
            
            provider_config = self.providers_config[provider_id]
            
            models = get_models_with_cache(
                provider_id,
                provider_config,
                api_key,
                use_cache=True
            )
            
            current_model = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(models)
            
            if current_model in models:
                self.model_combo.setCurrentText(current_model)
            
            QMessageBox.information(self, "成功", f"获取到 {len(models)} 个模型")
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"刷新失败: {str(e)}")
            
    def save_all_settings(self):
        """保存所有设置"""
        # 1. 保存API设置 (使用 ConfigManager 处理加密)
        from core.utils.config_manager import get_config_manager
        cm = get_config_manager()
        
        if 'api' not in self.settings:
            self.settings['api'] = {}
        
        self.settings['api']['provider'] = self.provider_combo.currentData()
        self.settings['api']['model'] = self.model_combo.currentText()
        
        # 获取输入的明文 Key
        plain_key = self.api_key_input.text().strip()
        # 更新内存中的配置（ ConfigManager.set_api_key 会处理加密）
        cm.config = self.settings
        cm.set_api_key(plain_key, cm.password)
        self.settings = cm.config
        
        self.settings['api']['batch_size_alignment'] = self.batch_size_alignment_spin.value()
        self.settings['api']['batch_size_lqa'] = self.batch_size_lqa_spin.value()
        
        # 2. 保存UI设置
        if 'ui' not in self.settings:
            self.settings['ui'] = {}
            
        self.settings['ui']['language'] = self.language_combo.currentData()
        self.settings['ui']['theme'] = self.theme_combo.currentData()
        self.settings['ui']['font_size'] = self.font_size_spin.value()
        self.settings['ui']['target_language'] = self.target_lang_combo.currentData()
        
        # 3. 保存高级设置
        if 'advanced' not in self.settings:
            self.settings['advanced'] = {}
            
        self.settings['advanced']['timeout'] = self.timeout_spin.value()
        self.settings['advanced']['timeout'] = self.timeout_spin.value()
        self.settings['advanced']['cache_ttl'] = self.cache_ttl_spin.value()
        self.settings['advanced']['log_level'] = self.log_level_combo.currentText()
        self.settings['advanced']['vlc_path'] = self.vlc_path_input.text().strip()
        
        # 4. 保存到文件
        self._save_settings_file()
        
        self.accept()
        
    def _save_settings_file(self):
        """保存主配置文件"""
        try:
            from core.utils.config_manager import get_config_manager
            get_config_manager().save(self.settings)
            logger.info("设置保存成功")
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            QMessageBox.warning(self, self.tr("错误"), self.tr("保存设置失败: {}").format(e))
            
    def save_settings(self):
        # 兼容旧方法名
        self.save_all_settings()
    
    def test_api_connection(self):
        """测试API连接"""
        provider_id = self.provider_combo.currentData()
        api_key = self.api_key_input.text().strip()
        model = self.model_combo.currentText()
        
        if not api_key:
            QMessageBox.warning(self, "提示", "请先输入API密钥")
            return
        
        if not model:
            QMessageBox.warning(self, "提示", "请选择模型")
            return
        
        try:
            from core.api.api_client import APIClient
            
            provider_config = self.providers_config[provider_id]
            client = APIClient(provider_config, api_key, model)
            
            response = client.generate_content(
                system_prompt="你是一个测试助手",
                user_prompt="请回复'连接成功'",
                json_mode=False
            )
            
            QMessageBox.information(self, "成功", f"API连接成功！\n\n响应: {response.get('text', '')[:100]}")
            
        except Exception as e:
            QMessageBox.warning(self, "失败", f"API连接失败: {str(e)}")
    
    def load_prompt_list(self):
        """加载Prompt列表"""
        prompt_dir = 'config/prompts'
        
        if not os.path.exists(prompt_dir):
            return
        
        # 系统保留的prompt（隐藏不显示）
        system_prompts = ['alignment', '.meta_prompt_generator']
        
        for filename in os.listdir(prompt_dir):
            if filename.endswith('.txt'):
                prompt_name = filename[:-4]
                # 跳过系统prompt
                if prompt_name not in system_prompts and not prompt_name.startswith('.'):
                    self.prompt_list.addItem(prompt_name)
    
    def on_prompt_selected(self, row):
        """Prompt选中"""
        if row < 0:
            return
        
        prompt_name = self.prompt_list.item(row).text()
        prompt_file = f'config/prompts/{prompt_name}.txt'
        
        if os.path.exists(prompt_file):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.prompt_preview.setPlainText(content)
            except Exception as e:
                logger.error(f"读取Prompt失败: {e}")
    
    def new_prompt(self):
        """新建Prompt"""
        from ui.dialogs.prompt_editor import PromptEditorDialog
        
        dialog = PromptEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 刷新列表
            self.prompt_list.clear()
            self.load_prompt_list()
            
            # 选中新创建的prompt
            prompt_name = dialog.get_prompt_name()
            items = self.prompt_list.findItems(prompt_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.prompt_list.setCurrentItem(items[0])
    
    def delete_prompt(self):
        """删除Prompt"""
        row = self.prompt_list.currentRow()
        if row < 0:
            return
        
        prompt_name = self.prompt_list.item(row).text()
        
        # 防止删除系统prompt
        system_prompts = ['alignment', '.meta_prompt_generator', 'lqa_strict', 'lqa_gentle']
        if prompt_name in system_prompts:
            QMessageBox.warning(self, "错误", f"'{prompt_name}' 是系统预设，不能删除")
            return
        
        reply = QMessageBox.question(
            self,
            "确认",
            f"确定删除 '{prompt_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            prompt_file = f'config/prompts/{prompt_name}.txt'
            try:
                if os.path.exists(prompt_file):
                    os.remove(prompt_file)
                self.prompt_list.takeItem(row)
                self.prompt_preview.clear()
                QMessageBox.information(self, "成功", "删除成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {str(e)}")
    
    def edit_prompt(self):
        """编辑选中的Prompt"""
        row = self.prompt_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一个Prompt")
            return
        
        prompt_name = self.prompt_list.item(row).text()
        
        from ui.prompt_editor import PromptEditorDialog
        
        dialog = PromptEditorDialog(prompt_name=prompt_name, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 刷新预览
            self.on_prompt_selected(row)
    
    def import_prompt(self):
        """导入Prompt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择Prompt文件",
            "",
            "Text Files (*.txt)"
        )
        
        if file_path:
            try:
                import shutil
                filename = os.path.basename(file_path)
                dest = f'config/prompts/{filename}'
                shutil.copy(file_path, dest)
                
                self.prompt_list.clear()
                self.load_prompt_list()
                
                QMessageBox.information(self, "成功", "导入成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导入失败: {str(e)}")
    
    def save_settings(self):
        """保存设置"""
        # 确保所有必要的键存在
        if 'api' not in self.settings:
            self.settings['api'] = {}
        if 'ui' not in self.settings:
            self.settings['ui'] = {}
        if 'advanced' not in self.settings:
            self.settings['advanced'] = {}
        if 'providers' not in self.settings:
            self.settings['providers'] = {}
        
        # 保存当前提供商的设置
        current_provider = self.provider_combo.currentData()
        self.settings['providers'][current_provider] = {
            'api_key': self.api_key_input.text().strip(),
            'model': self.model_combo.currentText()
        }
        
        # 更新全局设置
        self.settings['api']['provider'] = current_provider
        self.settings['api']['model'] = self.model_combo.currentText()
        self.settings['api']['api_key'] = self.api_key_input.text().strip()
        
        self.settings['ui']['language'] = self.language_combo.currentData()
        self.settings['ui']['font_size'] = self.font_size_spin.value()
        self.settings['ui']['theme'] = self.theme_combo.currentData()
        
        self.settings['advanced']['batch_size'] = self.batch_size_spin.value()
        self.settings['advanced']['timeout'] = self.timeout_spin.value()
        self.settings['advanced']['cache_ttl'] = self.cache_ttl_spin.value()
        self.settings['advanced']['log_level'] = self.log_level_combo.currentText()
        
        # 保存到文件
        settings_file = 'config/settings.json'
        try:
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, "成功", "设置已保存")
            self.accept()
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败: {str(e)}")
    
    def get_settings(self):
        """获取当前设置"""
        return self.settings
