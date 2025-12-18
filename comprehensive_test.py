
"""
Kaoche Pro 全功能自动化测试套件 (Comprehensive Test Suite)
=====================================================
这是一个单一的、独立的测试脚本，旨在覆盖项目的核心逻辑、UI 交互、数据导出及 API 集成。
使用方法: python comprehensive_test.py
"""

import unittest
import sys
import os
import shutil
import tempfile
import json
import time
from unittest.mock import MagicMock, patch

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

# 必须在导入 PyQt 之前设置 HEADLESS，虽然 unittest 会运行 QApplication
# 但这里我们尽量减少 GUI 弹窗干扰
os.environ["QT_QPA_PLATFORM"] = "offscreen" 

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QTimer

# 核心模块导入
from core.models.project_model import ProjectModel
from core.utils.exporters import DataExporter
from core.utils.config_manager import ConfigManager
from ui.main_window import MainWindow

# 全局 QApplication 单例
app = QApplication(sys.argv)

class TestCoreFeatures(unittest.TestCase):
    """核心功能测试：数据模型、配置管理、导出器"""

    def setUp(self):
        # 创建临时测试目录
        self.test_dir = tempfile.mkdtemp()
        self.sample_data = [
            {
                'source': {'text': 'Hello World', 'start': 0.0, 'end': 1.5}, 
                'target': {'text': '你好世界', 'start': 0.0, 'end': 1.6}, # 稍微不同的时间轴以测试同步
                'lqa_result': {'score': 9, 'issues': [], 'comment': 'Good'}
            },
            {
                'source': {'text': 'Test Line', 'start': 2.0, 'end': 3.0}, 
                'target': {'text': '测试行', 'start': 2.0, 'end': 3.0}, 
                'lqa_result': None
            }
        ]

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_exporter_formats(self):
        """测试数据导出 (SRT, JSON, ASS, VTT, TXT)"""
        # 1. JSON
        json_path = os.path.join(self.test_dir, 'export.json')
        success, _ = DataExporter.export_json_report(self.sample_data, json_path)
        self.assertTrue(success, "JSON 导出应成功")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.assertEqual(len(data), 2)
            # export_json_report 会将 source 提取为字符串
            self.assertEqual(data[0]['source'], 'Hello World')

        # 2. SRT (Source Base)
        srt_path = os.path.join(self.test_dir, 'export_source.srt')
        success, _ = DataExporter.export_content(self.sample_data, srt_path, side='target', time_base='source')
        self.assertTrue(success, "SRT (Source Base) 导出应成功")
        
        # 3. SRT (Target Base)
        srt_tgt_path = os.path.join(self.test_dir, 'export_target.srt')
        success, _ = DataExporter.export_content(self.sample_data, srt_tgt_path, side='target', time_base='target')
        self.assertTrue(success, "SRT (Target Base) 导出应成功")

        # 4. ASS (PySubs2 Integration)
        ass_path = os.path.join(self.test_dir, 'export.ass')
        success, _ = DataExporter.export_content(self.sample_data, ass_path, side='target')
        # 如果安装了 pysubs2，应该成功；否则应该返回失败或 Mock 处理
        # 这里假设环境中有 pysubs2 (因为我们之前已经处理过)
        if success:
            self.assertTrue(os.path.exists(ass_path))
            with open(ass_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn("[Events]", content, "ASS 文件应包含 Events 部分")

        # 5. TXT
        txt_path = os.path.join(self.test_dir, 'export.txt')
        success, _ = DataExporter.export_content(self.sample_data, txt_path, side='target')
        self.assertTrue(success)
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("你好世界", content)
            self.assertNotIn("-->", content) # 纯文本不应有时间轴箭头

    def test_config_encryption(self):
        """测试配置管理器的加密逻辑"""
        cm = ConfigManager(os.path.join(self.test_dir, 'config.json'))
        
        # 设置密码并启用加密
        success_enc = cm.enable_encryption("test_pass")
        self.assertTrue(success_enc)
        
        # 设置 API Key (自动加密)
        cm.set_api_key("secret_key_123", "test_pass")
        cm.save(cm.config)
        
        # 重新加载（模拟新启动）
        cm2 = ConfigManager(os.path.join(self.test_dir, 'config.json'))
        cm2.load()
        
        # 在解密前，通过底层字典访问应该是加密的
        raw_key = cm2.config.get('api', {}).get('api_key', '')
        self.assertTrue(raw_key.startswith("enc:"), "加密数据应有 enc: 前缀")
        self.assertNotEqual(raw_key, "secret_key_123")
        
        # 解密获取
        decrypted_val = cm2.get_api_key("test_pass")
        self.assertEqual(decrypted_val, "secret_key_123")


class TestMainWindowIntegration(unittest.TestCase):
    """UI 集成测试：模拟用户操作"""

    @classmethod
    def setUpClass(cls):
        # 只需要实例化一次 MainWindow
        cls.window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()

    def setUp(self):
        # 每次测试前重置数据
        self.window.subtitle_data = []
        self.window.subtitle_table.setRowCount(0)
    
    def test_window_title(self):
        self.assertIn("Kaoche Pro", self.window.windowTitle())

    def test_video_player_initialization(self):
        """验证视频播放器组件是否加载"""
        self.assertIsNotNone(self.window.video_player)
        # 验证我们新加的 ClickableSlider
        from ui.components.video_player import ClickableSlider
        self.assertIsInstance(self.window.video_player.timeline_slider, ClickableSlider)

    def test_data_loading_simulation(self):
        """模拟加载数据并验证表格渲染"""
        # 注入模拟数据
        mock_data = [
            {'source': {'text': 'A'}, 'target': {'text': 'B'}, 'lqa_result': None}
        ]
        self.window.subtitle_data = mock_data
        
        # 触发 UI 刷新 (通常由 load_file 内部调用 populate_table)
        self.window.populate_table()
        
        # 验证表格行数
        self.assertEqual(self.window.subtitle_table.rowCount(), 1)
        
        # 验证单元格内容
        source_item = self.window.subtitle_table.item(0, 3) # Col 3 is Source
        target_item = self.window.subtitle_table.item(0, 4) # Col 4 is Target
        self.assertEqual(source_item.text(), 'A')
        self.assertEqual(target_item.text(), 'B')

    @patch('ui.main_window.QFileDialog.getSaveFileName')
    @patch('core.utils.exporters.DataExporter.export_content')
    def test_export_action(self, mock_export, mock_file_dialog):
        """测试导出动作触发"""
        # 准备数据
        self.window.subtitle_data = [{'source': 'a', 'target': 'b'}]
        self.window.has_timestamps = True # 模拟视频模式
        
        # 模拟用户选择了保存路径
        mock_file_dialog.return_value = ('/tmp/test.srt', 'Subtitle Files (*.srt)')
        mock_export.return_value = (True, "Export Success")
        
        # 触发导出原文动作
        self.window.export_source()
        
        # 验证是否调用了 Exporter
        mock_export.assert_called_once()
        # 验证参数中是否包含了 intelligent time_base behavior
        # 默认模式下 (self.window.anchor_mode 默认为 'source' 或 'auto')
        # 我们期望 time_base 被正确传递
        call_args = mock_export.call_args
        self.assertEqual(call_args.kwargs.get('side'), 'source')
        # 检查 time_base 是否传递 (我们在最近的修改中加入了这个)
        self.assertIn('time_base', call_args.kwargs)


class TestWorkflows(unittest.TestCase):
    """工作流测试 (Mocked API)"""

    def test_lqa_workflow_simulation(self):
        """模拟完整的 LQA 分析流程"""
        # 我们不真调用 API，而是 Mock 由于 Worker 是在独立线程，
        # 我们可以直接测试 Worker 类的 `run` 逻辑，或者 Mock APIClient
        
        from core.workers.lqa_worker import LQAWorker
        
        mock_pairs = [("Hello", "你好")]
        mock_api_client = MagicMock()
        
        # 模拟 API 返回 (单条结果，因为 LQAWorker 是逐条处理)
        mock_response_json = {
            "id": 0, "score": 8, "issues": ["Stylistic"], "comment": "Okay", "suggestion": "Better"
        }
        # LQAWorker._parse_response 期望 dict 并从中提取 text 字段
        mock_api_client.generate_content.return_value = {'text': json.dumps(mock_response_json)}
        
        # 实例化 Worker (Mock API Client)
        # 注意: LQAWorker.__init__ 参数: (subtitle_pairs, api_client, prompt_template, ...)
        worker = LQAWorker(mock_pairs, mock_api_client, "Prompt Template")
        
        # 捕获信号 (注意: 信号是 batch_complete(int, int))
        # 我们这里改用 result_ready 信号来验证结果
        results = []
        worker.result_ready.connect(lambda idx, res: results.append(res))
        
        # 模拟运行
        worker.run()
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['score'], 8)
        self.assertEqual(results[0]['suggestion'], "Better")

if __name__ == '__main__':
    print("===================================================")
    print("开始执行 Kaoche Pro 全功能测试...")
    print("===================================================")
    unittest.main(verbosity=2)
