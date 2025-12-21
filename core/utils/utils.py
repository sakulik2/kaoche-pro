
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def detect_source_language(texts: List[str]) -> str:
    """
    自动检测原文语言
    
    Args:
        texts: 原文文本列表
        
    Returns:
        检测到的语言代码 (例如: 'en', 'zh-cn', 'unknown')
    """
    if not texts:
        return "unknown"
        
    try:
        from langdetect import detect
        from collections import Counter
        
        # 采样前50行非空文本 (增加采样数以覆盖混合语言)
        sample_texts = [t for t in texts if t.strip()][:50]
        if not sample_texts:
            return "unknown"
            
        # 统计检测结果
        langs = []
        for text in sample_texts:
            try:
                # langdetect 对短文本可能不准，但统计学上应该够用
                lang = detect(text)
                langs.append(lang)
            except:
                pass
                
        if not langs:
            return "unknown"
            
        # 分析语言分布
        counts = Counter(langs)
        total_count = len(langs)
        
        # 筛选占比超过 15% 的语言
        detected_langs = []
        for lang, count in counts.most_common():
            ratio = count / total_count
            if ratio >= 0.15:
                detected_langs.append(lang)
        
        if not detected_langs:
            return counts.most_common(1)[0][0]
            
        result = ", ".join(detected_langs)
        logger.info(f"自动检测语言: {result} (基于 {len(sample_texts)} 个样本, 来源分布: {dict(counts)})")
        return result
        
    except ImportError:
        logger.warning("未安装 langdetect 库，无法自动检测语言")
        return "unknown"
    except Exception as e:
        logger.error(f"语言检测失败: {e}")
        return "unknown"

def get_project_root() -> str:
    """
    获取项目根目录绝对路径
    
    Returns:
        项目根目录路径
    """
    import os
    # utils.py (core/utils/) -> core/ -> root/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    return os.path.dirname(parent_dir)

def detect_encoding(file_path: str) -> str:
    """自动检测字幕文件编码"""
    # 优先尝试 UTF-8
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8'
    except UnicodeDecodeError:
        pass
        
    # 尝试 GB18030 (兼容 GBK)
    try:
        with open(file_path, 'r', encoding='gb18030') as f:
            f.read()
        return 'gb18030'
    except UnicodeDecodeError:
        pass

    # 如果安装了 charset-normalizer 或 chardet 则尝试
    try:
        import charset_normalizer
        with open(file_path, 'rb') as f:
            result = charset_normalizer.detect(f.read())
            if result and result.get('encoding'):
                return result['encoding']
    except ImportError:
        try:
            import chardet
            with open(file_path, 'rb') as f:
                result = chardet.detect(f.read())
                if result and result.get('encoding'):
                    return result['encoding']
        except ImportError:
            pass

    return 'utf-8' # 最终保底

