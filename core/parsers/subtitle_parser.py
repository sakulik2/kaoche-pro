"""
字幕文件解析模块
支持 SRT, ASS, VTT, TXT 格式
"""

import pysubs2
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


from core.models.subtitle import SubtitleItem

def parse_subtitle_file(file_path: str) -> List[SubtitleItem]:
    """
    通用字幕文件解析函数，支持 SRT, ASS, VTT
    
    Args:
        file_path: 字幕文件路径
        
    Returns:
        字幕数据列表 (SubtitleItem)
    """
    try:
        subs = pysubs2.load(file_path)
        parsed = []
        
        for i, line in enumerate(subs):
            # 基础清理
            text = line.plaintext.strip()
            
            # ASS 特殊处理：将 ASS 的硬换行 \N 替换为换行符
            text = text.replace(r"\N", "\n").replace(r"\n", "\n")
            
            parsed.append(SubtitleItem(
                text=text,
                start=line.start / 1000.0,  # 转换为秒
                end=line.end / 1000.0,      # 转换为秒
                index=i
            ))
            
        logger.info(f"成功解析字幕文件: {file_path}, 共 {len(parsed)} 行")
        return parsed
        
    except Exception as e:
        logger.error(f"解析字幕文件 {file_path} 失败: {e}")
        return []


def parse_plain_text_file(file_path: str) -> List[str]:
    """
    解析纯文本文件（每行一个字幕）
    
    Args:
        file_path: 文本文件路径
        
    Returns:
        文本行列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        logger.info(f"成功解析文本文件: {file_path}, 共 {len(lines)} 行")
        return lines
        
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            logger.info(f"使用 GBK 编码解析文本文件: {file_path}")
            return lines
        except Exception as e:
            logger.error(f"解析文本文件 {file_path} 失败: {e}")
            return []
    except Exception as e:
        logger.error(f"解析文本文件 {file_path} 失败: {e}")
        return []


def clean_ass_text(text: str) -> str:
    """
    强力清洗 ASS/SSA 标签
    
    Args:
        text: 包含 ASS 标签的文本
        
    Returns:
        清洗后的纯文本
    """
    import re
    
    # 1. 移除 ASS 标签 { ... }
    text = re.sub(r'\{[^}]+\}', '', text)
    
    # 2. 移除常见的转义换行
    text = text.replace(r'\N', ' ').replace(r'\n', ' ').replace(r'\h', ' ')
    
    # 3. 移除多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def detect_file_type(file_path: str) -> str:
    """
    自动检测文件类型
    
    Returns:
        'srt', 'ass', 'vtt', 'txt' 或 'unknown'
    """
    ext = file_path.lower().split('.')[-1]
    
    if ext in ['srt', 'ass', 'ssa', 'vtt']:
        return ext
    elif ext in ['txt', 'text']:
        return 'txt'
    else:
        return 'unknown'
