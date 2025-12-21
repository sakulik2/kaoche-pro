import unittest
import os
import shutil
from PyQt6.QtCore import QCoreApplication
import sys
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# 必须先创建 App 才能测试 QObject 信号
app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication(sys.argv)

from tools.SubStudio.core.subtitle_store import SubtitleStore

class TestSubtitleStore(unittest.TestCase):
    def setUp(self):
        self.store = SubtitleStore()
        self.test_srt = "test_data.srt"
        with open(self.test_srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nHello World\n\n")

    def tearDown(self):
        if os.path.exists(self.test_srt):
            os.remove(self.test_srt)
        if os.path.exists("test_out.ass"):
            os.remove("test_out.ass")

    def test_load_and_save(self):
        self.store.load_file(self.test_srt)
        self.assertEqual(len(self.store.subs), 1)
        self.assertEqual(self.store.subs[0].text, "Hello World")
        
        # Test Save
        self.store.save_file("test_out.ass")
        self.assertTrue(os.path.exists("test_out.ass"))

    def test_add_and_sort(self):
        self.store.load_file(self.test_srt)
        # 插入一个更早的时间
        self.store.add_event(0, 500, "Intro")
        
        events = self.store.get_all_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].text, "Intro") # 应该在第一位
        self.assertEqual(events[1].text, "Hello World")
        self.assertTrue(self.store.is_dirty)

    def test_update(self):
        self.store.load_file(self.test_srt)
        self.store.update_event(0, text="Modified")
        self.assertEqual(self.store.get_event(0).text, "Modified")
        self.assertTrue(self.store.is_dirty)

    def test_delete(self):
        self.store.load_file(self.test_srt)
        self.store.delete_events([0])
        self.assertEqual(len(self.store.subs), 0)
        self.assertTrue(self.store.is_dirty)

if __name__ == "__main__":
    unittest.main()
