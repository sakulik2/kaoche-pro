import pytest
from PyQt6.QtCore import Qt
from ui.sections.subtitle_table import SubtitleTable
from ui.sections.log_panel import LogPanel
from ui.sections.lqa_details_panel import LQADetailsPanel

def test_subtitle_table_data_loading(qtbot, sample_subtitle_data):
    table = SubtitleTable()
    qtbot.addWidget(table)
    
    # 测试数据加载
    table.set_data(sample_subtitle_data, has_timestamps=True)
    assert table.rowCount() == 2
    assert table.item(0, 3).text() == "Hello World"
    assert table.item(1, 5).text() == "9" # 评分列

def test_subtitle_table_signals(qtbot, sample_subtitle_data):
    table = SubtitleTable()
    qtbot.addWidget(table)
    table.set_data(sample_subtitle_data)
    
    # 模拟选择行
    with qtbot.waitSignal(table.row_selected) as blocker:
        table.selectRow(0)
    
    assert blocker.args[0] == 0
    assert blocker.args[1]['source']['text'] == 'Hello World'

def test_log_panel_append(qtbot):
    panel = LogPanel()
    qtbot.addWidget(panel)
    
    panel.append_log("Test Log Message")
    # 内容包含时间戳，所以用 in
    assert "Test Log Message" in panel.log_output.toPlainText()

def test_lqa_details_display(qtbot):
    panel = LQADetailsPanel()
    qtbot.addWidget(panel)
    
    details_text = "评分: 8\n问题: Grammar\n建议: Needs improvement"
    panel.set_details(details_text)
    
    text = panel.lqa_details.toPlainText()
    assert "8" in text
    assert "Grammar" in text
    assert "Needs improvement" in text
