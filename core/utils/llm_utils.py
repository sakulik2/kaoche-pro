"""
LLM 相关通用工具函数
包含：
1. 鲁棒的 JSON 解析
2. 重试机制
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union, Callable

logger = logging.getLogger(__name__)


def parse_json_from_response(content: str) -> Union[Dict, List, None]:
    """
    从 LLM 响应中鲁棒地解析 JSON
    
    策略：
    1. 尝试直接解析
    2. 尝试剥离 Markdown 代码块
    3. 尝试提取 JSON 结构 ({} 或 [])
    4. 尝试截断修复 (针对截断的 JSON)
    
    Args:
        content: LLM 返回的文本内容
        
    Returns:
        解析后的对象 (Dict or List)，失败返回 None
    """
    if not content:
        return None
        
    content = content.strip()
    
    # 1. 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
        
    # 2. 处理 Markdown 代码块 (```json ... ```)
    # 兼容 ```json, ```JSON, 或仅仅 ```
    if '```' in content:
        match = re.search(r'```(?:json|JSON)?\s*([\s\S]*?)```', content)
        if match:
            clean_content = match.group(1).strip()
            try:
                return json.loads(clean_content)
            except json.JSONDecodeError:
                pass # 继续尝试其他方法
                
        # 可能是只有开头没有结尾
        if content.startswith('```'):
            lines = content.split('\n')
            # 只有当最后一行也是 ``` 才移除最后一行
            if lines[-1].strip().startswith('```'):
                 clean_content = '\n'.join(lines[1:-1])
            else:
                 clean_content = '\n'.join(lines[1:])
            
            try:
                return json.loads(clean_content)
            except json.JSONDecodeError:
                pass

    # 3. 尝试正则提取 JSON 结构
    # 寻找最外层的 [] 或 {}
    try:
        # 尝试找数组
        match_list = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
        if match_list:
            return json.loads(match_list.group())
            
        # 尝试找对象
        match_dict = re.search(r'\{.*\}', content, re.DOTALL)
        if match_dict:
            return json.loads(match_dict.group())
    except json.JSONDecodeError:
        pass
        
    # 4. 二次尝试：截断修复
    # 有时API会在JSON后添加额外文本，或者JSON本身截断
    # 尝试寻找最后一个 ] 或 }
    last_bracket = content.rfind(']')
    last_brace = content.rfind('}')
    end_idx = max(last_bracket, last_brace)
    
    if end_idx != -1:
        try:
            return json.loads(content[:end_idx+1])
        except json.JSONDecodeError:
            pass
            
    logger.warning("JSON 解析失败，所有策略均无效")
    return None


def retry_operation(
    func: Callable, 
    max_retries: int = 3, 
    delay: float = 1.0, 
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    通用重试装饰器/函数
    
    Args:
        func: 要执行的函数 (无参)
        max_retries: 最大重试次数
        delay: 初始延迟秒数
        backoff: 延迟倍数
        exceptions: 需要捕获的异常类型元组
    
    Returns:
        函数执行结果
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                sleep_time = delay * (backoff ** attempt)
                logger.warning(f"操作失败: {e}，将在 {sleep_time:.1f} 秒后重试 ({attempt+1}/{max_retries})")
                time.sleep(sleep_time)
            else:
                logger.error(f"操作失败，已达到最大重试次数: {e}")
                
    raise last_exception
