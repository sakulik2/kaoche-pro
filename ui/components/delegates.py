from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath

class ScoreDelegate(QStyledItemDelegate):
    """
    高对比度评分代理
    在彩色背景上绘制带有描边的文字
    """
    def paint(self, painter, option, index):
        painter.save()
        
        # 1. 绘制背景
        # 获取背景色
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg_color and isinstance(bg_color, QColor):
            painter.fillRect(option.rect, bg_color)
        
        # 2. 绘制文字 (高对比度描边)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            # 设置字体
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            
            # 计算位置 (居中)
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            text_height = fm.ascent() # cap height approx
            
            x = option.rect.x() + (option.rect.width() - text_width) / 2
            y = option.rect.y() + (option.rect.height() + text_height) / 2 - fm.descent()
            
            # 创建路径
            path = QPainterPath()
            path.addText(x, y, font, text)
            
            # 绘制描边 (黑色，粗)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.strokePath(path, QPen(QColor(0, 0, 0), 3))
            
            # 绘制填充 (白色)
            painter.fillPath(path, QColor(255, 255, 255))
            
        painter.restore()
