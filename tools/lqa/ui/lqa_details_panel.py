"""
LQA 详情面板组件
"""

from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QTextEdit
from PyQt6.QtCore import pyqtSlot
import logging

logger = logging.getLogger(__name__)

class LQADetailsPanel(QGroupBox):
    """LQA 详情面板组件"""
    
    def __init__(self, title="LQA 分析结果", parent=None):
        super().__init__(title, parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.lqa_details = QTextEdit()
        self.lqa_details.setReadOnly(True)
        self.lqa_details.setPlaceholderText(self.tr("选择一行查看详细的LQA分析结果"))
        layout.addWidget(self.lqa_details)
        
    @pyqtSlot(str)
    def set_details(self, details: str):
        """设置详情文本"""
        self.lqa_details.setPlainText(details)
        
    def clear(self):
        """清空详情"""
        self.lqa_details.clear()
        self.lqa_details.setPlaceholderText(self.tr("选择一行查看详细的LQA分析结果"))
