from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QGroupBox, QTableWidget, QTableWidgetItem, 
                             QWidget, QHeaderView, QPushButton, QDialogButtonBox)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont
from collections import Counter

class ScoreHistogram(QWidget):
    """分数分布直方图"""
    def __init__(self, scores):
        super().__init__()
        self.scores = scores
        self.setMinimumHeight(150)
        self.setStyleSheet("background-color: white; border-radius: 4px;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Buckets: <5 (Red), 5-8 (Yellow), >=8 (Green)
        low = len([s for s in self.scores if s < 5])
        mid = len([s for s in self.scores if 5 <= s < 8])
        high = len([s for s in self.scores if s >= 8])
        
        # Draw Bars
        width = self.width()
        height = self.height()
        
        counts = [low, mid, high]
        max_count = max(counts) if counts else 1
        labels = ["< 5", "5 - 7.9", ">= 8"]
        colors = [QColor(255, 200, 200), QColor(255, 255, 200), QColor(200, 255, 200)]
        
        # Calculate dimensions
        bar_width = width / 5
        x_start = width / 10
        gap = width / 10 * 3  # Spacing between centers
        
        for i, count in enumerate(counts):
            # Center x
            x_center = (i + 0.5) * (width / 3)
            x_left = x_center - bar_width / 2
            
            # Height
            bar_height = (count / max_count) * (height - 50) if max_count > 0 else 0
            
            # Rect
            rect = QRectF(x_left, height - bar_height - 25, bar_width, bar_height)
            
            # Draw Bar
            painter.setBrush(colors[i])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 4, 4)
            
            # Draw Count
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(QRectF(x_left, height - bar_height - 45, bar_width, 20), 
                             Qt.AlignmentFlag.AlignCenter, str(count))
            
            # Draw Label
            painter.drawText(QRectF(x_left, height - 20, bar_width, 20), 
                             Qt.AlignmentFlag.AlignCenter, labels[i])


class GlobalReportDialog(QDialog):
    """全局分析报告对话框"""
    def __init__(self, subtitle_data, parent=None):
        super().__init__(parent)
        self.data = subtitle_data
        self.main_window = parent
        self.setWindowTitle("全局分析报告")
        self.setMinimumWidth(800)
        self.setMinimumHeight(700)
        
        self.global_ai_result = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Statistics
        stats_group = QGroupBox("统计概览")
        stats_layout = QHBoxLayout()
        
        checked = [item for item in self.data if item.get('lqa_result')]
        scores = [item['lqa_result'].get('score', 0) for item in checked]
        
        total_lines = len(self.data)
        checked_count = len(checked)
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Style logic
        score_color = "green" if avg_score >= 8 else "orange" if avg_score >= 5 else "red"
        
        lbl_score = QLabel(f"<div style='text-align:center;'><h1 style='color:{score_color}; font-size: 36px;'>{avg_score:.1f}</h1><p>平均分</p></div>")
        lbl_progress = QLabel(f"<div style='text-align:center;'><h1>{checked_count} / {total_lines}</h1><p>已检查行数</p></div>")
        lbl_rate = QLabel(f"<div style='text-align:center;'><h1>{checked_count/total_lines*100:.0f}%</h1><p>完成率</p></div>")
        
        stats_layout.addWidget(lbl_score)
        stats_layout.addWidget(lbl_progress)
        stats_layout.addWidget(lbl_rate)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # 2. Histogram
        hist_group = QGroupBox("分数分布")
        hist_layout = QVBoxLayout()
        hist_layout.addWidget(ScoreHistogram(scores))
        hist_group.setLayout(hist_layout)
        layout.addWidget(hist_group)
        
        # 3. Top Issues
        issues_group = QGroupBox("高频问题")
        issues_layout = QVBoxLayout()
        
        issue_list = []
        for item in checked:
            issues = item['lqa_result'].get('issues', [])
            issue_list.extend(issues)
            
        counter = Counter([i for i in issue_list if i and i != "无"])
        top_issues = counter.most_common(10)
        
        # Table
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["问题类型", "出现次数"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setRowCount(len(top_issues))
        
        for i, (issue, count) in enumerate(top_issues):
            table.setItem(i, 0, QTableWidgetItem(issue))
            table.setItem(i, 1, QTableWidgetItem(str(count)))
            
        issues_layout.addWidget(table)
        issues_group.setLayout(issues_layout)
        layout.addWidget(issues_group)
        
        # 4. AI Deep Review Section
        self.ai_group = QGroupBox("AI 深度分析 (全篇审核)")
        ai_layout = QVBoxLayout()
        
        self.ai_summary_label = QLabel("全篇一致性、语气连贯性及术语深度审查报告。")
        self.ai_summary_label.setWordWrap(True)
        self.ai_summary_label.setStyleSheet("color: #666; font-style: italic;")
        ai_layout.addWidget(self.ai_summary_label)
        
        self.run_ai_btn = QPushButton("🚀 运行 AI 深层审查")
        self.run_ai_btn.setFixedHeight(40)
        self.run_ai_btn.clicked.connect(self.run_global_ai_analysis)
        ai_layout.addWidget(self.run_ai_btn)
        
        self.ai_result_text = QTextEdit()
        self.ai_result_text.setReadOnly(True)
        self.ai_result_text.setVisible(False)
        ai_layout.addWidget(self.ai_result_text)
        
        self.ai_group.setLayout(ai_layout)
        layout.addWidget(self.ai_group)
        
        # Close Button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def run_global_ai_analysis(self):
        """运行全局 AI 分析"""
        if not self.main_window:
            return
            
        api_client = self.main_window.get_api_client()
        if not api_client:
            return
            
        self.run_ai_btn.setEnabled(False)
        self.run_ai_btn.setText("⏳ 正在分析全篇 (预计 1-2 分钟)...")
        
        # 加载模板
        from core.services.lqa_processor import load_prompt_template
        template = load_prompt_template("lqa_global.txt")
        
        # 准备数据
        all_pairs = []
        for i, item in enumerate(self.data):
             source = item.get('source', {})
             target = item.get('target', {})
             all_pairs.append({
                 "id": i + 1,
                 "source": source.get('text', '') if isinstance(source, dict) else str(source),
                 "target": target.get('text', '') if isinstance(target, dict) else str(target)
             })
             
        # 启动 Worker
        from core.workers.lqa_worker import GlobalLQAWorker
        self.worker = GlobalLQAWorker(
            all_pairs,
            api_client,
            template,
            context=getattr(self.main_window, 'global_context', ""),
            target_language="zh_CN"
        )
        self.worker.finished.connect(self.on_ai_analysis_finished)
        self.worker.error_occurred.connect(self.on_ai_analysis_error)
        self.worker.start()

    def on_ai_analysis_finished(self, result):
        """分析完成"""
        self.run_ai_btn.setVisible(False)
        self.ai_result_text.setVisible(True)
        self.global_ai_result = result
        
        # 格式化展示
        summary = result.get('global_summary', '无摘要')
        score = result.get('global_score', 0)
        issues = result.get('consistency_issues', [])
        errors = result.get('major_errors', [])
        
        report = f"## 综合评分: {score}/100\n\n"
        report += f"### 总体评价:\n{summary}\n\n"
        
        if issues:
            report += "### 一致性问题:\n"
            for issue in issues:
                report += f"- {issue}\n"
            report += "\n"
            
        if errors:
            report += "### 重大错误:\n"
            for error in errors:
                report += f"- {error}\n"
        
        self.ai_result_text.setMarkdown(report)
        
    def on_ai_analysis_error(self, error_msg):
        """分析错误"""
        self.run_ai_btn.setEnabled(True)
        self.run_ai_btn.setText("🚀 重新运行 AI 深层审查")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "分析失败", f"AI 深度分析失败: {error_msg}")
