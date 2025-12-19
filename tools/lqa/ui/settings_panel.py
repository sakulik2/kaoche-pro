from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QSpinBox, QComboBox, QGroupBox, QLabel
from PyQt6.QtCore import Qt

class LqaSettingsPanel(QWidget):
    """LQA 专属设置面板"""
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("LQA 运行参数")
        form = QFormLayout(group)
        
        self.batch_size_alignment = QSpinBox()
        self.batch_size_alignment.setRange(1, 100)
        form.addRow("对齐批处理大小:", self.batch_size_alignment)
        
        self.batch_size_lqa = QSpinBox()
        self.batch_size_lqa.setRange(1, 100)
        form.addRow("分析批处理大小:", self.batch_size_lqa)
        
        self.target_lang = QComboBox()
        self.target_lang.addItems(["zh_CN", "en_US", "ja_JP", "ko_KR"])
        form.addRow("默认目标语言:", self.target_lang)
        
        layout.addWidget(group)
        
        info = QLabel("提示: 此处的设置仅影响 LQA 工具的运行逻辑。")
        info.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 10px;")
        layout.addWidget(info)
        
        layout.addStretch()

    def load_settings(self):
        if not self.hub or not self.hub.config: return
        settings = self.hub.config.load()
        
        # 加载 LQA 相关配置
        api_cfg = settings.get('api', {})
        self.batch_size_alignment.setValue(api_cfg.get('batch_size_alignment', 10))
        self.batch_size_lqa.setValue(api_cfg.get('batch_size_lqa', 5))
        
        ui_cfg = settings.get('ui', {})
        target_lang = ui_cfg.get('target_language', 'zh_CN')
        idx = self.target_lang.findText(target_lang)
        if idx >= 0: self.target_lang.setCurrentIndex(idx)

    def save_settings(self):
        """此方法由 SettingsDialog 在保存时调用"""
        if not self.hub or not self.hub.config: return
        settings = self.hub.config.load()
        
        if 'api' not in settings: settings['api'] = {}
        settings['api']['batch_size_alignment'] = self.batch_size_alignment.value()
        settings['api']['batch_size_lqa'] = self.batch_size_lqa.value()
        
        if 'ui' not in settings: settings['ui'] = {}
        settings['ui']['target_language'] = self.target_lang.currentText()
        
        self.hub.config.save(settings)
