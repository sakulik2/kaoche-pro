import pytest
import sys
import os
from PyQt6.QtWidgets import QApplication

# 确保核心模块可导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session")
def qapp():
    """提供单例 QApplication"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
def project_model():
    """注入 ProjectModel 实例"""
    from core.models.project_model import ProjectModel
    return ProjectModel()

@pytest.fixture
def sample_subtitle_data():
    """提供样例字幕数据"""
    return [
        {
            'source': {'text': 'Hello World', 'start': 0.0, 'end': 2.0},
            'target': {'text': '你好世界'},
            'lqa_result': None
        },
        {
            'source': {'text': 'Testing Framework', 'start': 2.5, 'end': 4.5},
            'target': {'text': '测试框架'},
            'lqa_result': {'score': 9, 'issues': [], 'comment': 'Good'}
        }
    ]
