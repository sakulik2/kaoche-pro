import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QSignalSpy
from tools.SubStudio.core.subtitle_store import SubtitleStore
from tools.SubStudio.ui.components.style_editor import StyleEditorWidget

class TestSubStudioPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 创建一个全局唯一的 QApplication 实例用于测试
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = SubtitleStore()
        # 注入一点模拟数据
        from pysubs2 import SSAEvent
        self.store.subs.events.append(SSAEvent(start=1000, end=2000, text="Test 1"))
        self.store.subs.events.append(SSAEvent(start=3000, end=4000, text="Test 2"))

    def test_granular_signaling_performance(self):
        """验证单条字幕修改时发送的是局部信号而非全量信号"""
        spy_data = QSignalSpy(self.store.dataChanged)
        spy_events = QSignalSpy(self.store.eventsChanged)
        
        # 修改文本（内容性变更）
        self.store.update_event(0, text="Modified")
        
        self.assertEqual(len(spy_events), 1, "应该触局部事件变更信号")
        self.assertEqual(len(spy_data), 0, "不应该触发全量数据变更信号（避免全量刷新卡顿）")
        
        # 修改时间（结构性变更）
        self.store.update_event(0, start=5000)
        self.assertEqual(len(spy_data), 1, "修改时间导致排序变化，应该触发全量刷新")

    def test_style_preview_mapping(self):
        """验证样式编辑器参数调整时能正确发射实时预览信号"""
        editor = StyleEditorWidget(self.store)
        spy_preview = QSignalSpy(editor.previewRequested)
        
        # 模拟修改字号
        editor.update_style("fontsize", 30)
        
        self.assertEqual(len(spy_preview), 1, "应该发射预览请求信号")
        style = spy_preview[0][0]
        self.assertEqual(style.fontsize, 30, "预览样式中的字号应为最新修改值")

if __name__ == "__main__":
    unittest.main()
