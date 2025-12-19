import os
import logging
import pysubs2
from typing import Optional

logger = logging.getLogger(__name__)

from core.utils.utils import detect_encoding

def convert_subtitle(src_path: str, dst_path: str, encoding: str = "UTF-8", strip_styles: bool = True):
    """
    通用转换函数
    src_path: 源文件路径
    dst_path: 目标文件路径
    encoding: 输出编码
    strip_styles: 是否清除样式 (ASS -> SRT)
    """
    ext = os.path.splitext(dst_path)[1].lower()
    
    # 1. 加载源文件
    try:
        # 先自动检测输入编码
        input_enc = detect_encoding(src_path)
        subs = pysubs2.load(src_path, encoding=input_enc)
    except Exception as e:
        logger.error(f"加载字幕失败: {src_path}, {e}")
        # 最后的挣扎：不带参数加载
        try:
            subs = pysubs2.load(src_path)
        except:
            raise ValueError(f"无法读取文件: {e}")

    # 2. 处理样式 (如果需要)
    if strip_styles and ext == ".srt":
        # SRT 不支持复杂的样式和绘图，pysubs2 在保存时会自动处理，
        # 但我们可以显式清除一些标记。
        for line in subs:
            # 简单清理一些 ASS 标签 (如果是从 ASS 转过来)
            pass

    # 3. 执行导出
    if ext in [".srt", ".ass", ".vtt", ".ssa"]:
        subs.save(dst_path, encoding=encoding)
    elif ext == ".xlsx":
        export_to_xlsx(subs, dst_path)
    elif ext == ".txt":
        export_to_txt(subs, dst_path, encoding)
    else:
        raise ValueError(f"不支持的导出格式: {ext}")

def export_to_xlsx(subs: pysubs2.SSAFile, dst_path: str):
    """导出到 Excel (XLSX)"""
    try:
        from openpyxl import Workbook
    except ImportError:
        logger.error("未安装 openpyxl, 无法导出 XLSX")
        raise RuntimeError("请安装 openpyxl 以支持 Excel 导出")

    wb = Workbook()
    ws = wb.active
    ws.title = "Subtitles"
    
    # 表头
    ws.append(["Index", "Start", "End", "Text", "Duration (ms)"])
    
    for i, line in enumerate(subs):
        ws.append([
            i + 1,
            pysubs2.time.ms_to_str(line.start),
            pysubs2.time.ms_to_str(line.end),
            line.plaintext,
            line.end - line.start
        ])
    
    wb.save(dst_path)

def export_to_txt(subs: pysubs2.SSAFile, dst_path: str, encoding: str):
    """纯文本导出 (仅内容)"""
    with open(dst_path, "w", encoding=encoding) as f:
        for line in subs:
            f.write(line.plaintext + "\n")
