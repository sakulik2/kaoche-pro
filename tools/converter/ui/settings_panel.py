from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QGroupBox, QLabel
from PyQt6.QtCore import Qt

class ConverterSettingsPanel(QWidget):
    """字幕转换器专属设置"""
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        
        group = QGroupBox("转换偏好")
        form = QFormLayout(group)
        
        self.default_encoding = QComboBox()
        self.default_encoding.addItems(["UTF-8", "GB18030", "UTF-16", "Big5"])
        form.addRow("输出编码:", self.default_encoding)
        
        self.overwrite_original = QCheckBox("覆盖原始文件")
        form.addRow("", self.overwrite_original)
        
        self.clear_styles = QCheckBox("转换时清除样式 (如 ASS -> SRT)")
        self.clear_styles.setChecked(True)
        form.addRow("", self.clear_styles)
        
        layout.addWidget(group)
        layout.addStretch()

    def load_settings(self):
        if not self.hub or not self.hub.config: return
        settings = self.hub.config.load().get('converter', {})
        
        self.default_encoding.setCurrentText(settings.get('encoding', 'UTF-8'))
        self.overwrite_original.setChecked(settings.get('overwrite', False))
        self.clear_styles.setChecked(settings.get('clear_styles', True))

    def save_settings(self):
        if not self.hub or not self.hub.config: return
        settings = self.hub.config.load()
        if 'converter' not in settings: settings['converter'] = {}
        
        settings['converter']['encoding'] = self.default_encoding.currentText()
        settings['converter']['overwrite'] = self.overwrite_original.isChecked()
        settings['converter']['clear_styles'] = self.clear_styles.isChecked()
        
        self.hub.config.save(settings)
