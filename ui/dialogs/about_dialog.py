import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QFont, QIcon

class AboutDialog(QDialog):
    """关于对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 kaoche-pro")
        self.setFixedSize(500, 350)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 顶部区域：大图标 + 标题
        top_layout = QHBoxLayout()
        top_layout.setSpacing(20)
        
        # 图标 (尝试加载应用图标，如果没有则显示默认文本)
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            icon_label.setPixmap(pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            # Fallback style
            icon_label.setText("KP")
            icon_label.setStyleSheet("font-size: 40px; font-weight: bold; color: white; background-color: #2196F3; border-radius: 10px;")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setFixedSize(80, 80)
            
        top_layout.addWidget(icon_label)
        
        # 标题和版本信息
        title_layout = QVBoxLayout()
        title_label = QLabel("kaoche-pro")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        ver_label = QLabel("Version 1.0.0")
        ver_label.setStyleSheet("color: #666; font-size: 14px;")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(ver_label)
        title_layout.addStretch()
        
        top_layout.addLayout(title_layout)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        
        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 描述与版权
        desc_label = QLabel(
            "AI 驱动的本地化 LQA 与字幕审校工具。\n"
            "旨在为本地化工程师提供高效、智能的审校体验。"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        layout.addWidget(desc_label)
        
        # 作者与协议
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(5)
        
        author_label = QLabel("Author: sakulik")
        author_label.setStyleSheet("font-weight: bold;")
        
        license_label = QLabel("License: MIT License")
        license_label.setStyleSheet("color: #666;")
        
        meta_layout.addWidget(author_label)
        meta_layout.addWidget(license_label)
        
        layout.addLayout(meta_layout)
        
        layout.addStretch()
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("确定")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
