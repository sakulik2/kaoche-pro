"""
日志面板组件
"""

from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QTextEdit
from PyQt6.QtCore import pyqtSlot
import logging

logger = logging.getLogger(__name__)

class LogPanel(QGroupBox):
    """日志面板组件"""
    
    def __init__(self, title="📋 日志", parent=None):
        super().__init__(title, parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(100)
        layout.addWidget(self.log_output)
        
    @pyqtSlot(str)
    def append_log(self, message: str):
        """记录日志"""
        self.log_output.append(message)
        logger.info(message)
        
    def clear(self):
        """清空日志"""
        self.log_output.clear()
