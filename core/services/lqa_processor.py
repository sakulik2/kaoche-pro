"""
LQA (Localization Quality Assurance) 核心处理模块
"""

import json
import logging
from typing import List, Dict, Any, Optional
from core.api.api_client import APIClient

logger = logging.getLogger(__name__)


def load_prompt_template(prompt_file: str) -> str:
    """
    加载 Prompt 模板文件
    
    Args:
        prompt_file: Prompt 文件路径 (相对于 config/prompts/)
        
    Returns:
        Prompt 模板文本
    """
    try:
        from core.utils.utils import get_project_root
        import os
        
        root = get_project_root()
        path = os.path.join(root, "config", "prompts", prompt_file)
        
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"加载 Prompt 模板失败: {e}")
        return ""


def format_prompt(template: str, context: str = "", target_language: str = "zh_CN", source_language: str = "auto") -> str:
    """
    格式化 Prompt 模板，替换占位符
    
    Args:
        template: Prompt 模板
        context: 上下文/辩解文本
        target_language: 目标语言代码 (e.g. zh_CN, en_US)
        source_language: 原文语言代码
        
    Returns:
        格式化后的 Prompt
    """
    prompt = template.replace("{context}", context)
    prompt = prompt.replace("{target_language}", target_language)
    prompt = prompt.replace("{source_language}", source_language)
    return prompt


def process_lqa_batch(
    api_client: APIClient,
    source_batch: List[str],
    target_batch: List[str],
    prompt_template: str,
    context: str = "",
    target_language: str = "zh_CN",
    source_language: str = "auto",
    start_index: int = 0
) -> List[Dict[str, Any]]:
    """
    处理一批 LQA 检查
    
    Args:
        api_client: API 客户端
        source_batch: 原文批次
        target_batch: 译文批次
        prompt_template: Prompt 模板
        context: 用户上下文
        target_language: 目标语言
        source_language: 原文语言
        start_index: 起始索引
        
    Returns:
        LQA 结果列表
    """
    # 构建输入数据
    pairs = []
    for i, (src, tgt) in enumerate(zip(source_batch, target_batch)):
        pairs.append({
            "id": start_index + i,
            "source": src,
            "target": tgt
        })
    
    # 格式化 Prompt
    system_prompt = format_prompt(prompt_template, context, target_language, source_language)
    user_prompt = json.dumps(pairs, ensure_ascii=False)
    
    try:
        # 调用 API
        response = api_client.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
            temperature=1.0
        )
        
        # 解析响应
        from core.utils.llm_utils import parse_json_from_response
        results = parse_json_from_response(response['text'])
        
        if results is None:
            raise json.JSONDecodeError("Failed to parse JSON", response['text'], 0)

        
        # 处理可能的嵌套结构 {"reviews": [...]}
        if isinstance(results, dict) and "reviews" in results:
            results = results["reviews"]
        elif not isinstance(results, list):
            # 如果是单个对象，包装成列表
            if isinstance(results, dict):
                 results = [results]
            else:
                 results = []
        
        # 确保 ID 正确
        for idx, item in enumerate(results):
            if 'id' not in item or item['id'] >= start_index + len(source_batch):
                item['id'] = start_index + idx
        
        logger.info(f"批次 LQA 检查完成: {len(results)} 个结果")
        return results
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        logger.error(f"响应内容: {response.get('text', '')[:500]}")
        return []
    except Exception as e:
        logger.error(f"LQA 批次处理失败: {e}", exc_info=True)
        return []


def validate_lqa_result(result: Any) -> bool:
    """
    验证 LQA 结果的完整性
    支持字典或 SubtitlePair 实例
    
    Returns:
        True if valid
    """
    required_fields = ['id', 'score', 'issues', 'comment', 'suggestion']
    
    if isinstance(result, dict):
        return all(field in result for field in required_fields)
    
    # 假设 lqa_result 存在于某种模型中
    return hasattr(result, 'lqa_result') and result.lqa_result is not None


def merge_lqa_results(results_list: List[List[Dict]]) -> Dict[int, Dict]:
    """
    合并多个批次的 LQA 结果
    
    Args:
        results_list: 批次结果列表
        
    Returns:
        {row_id: result} 字典
    """
    merged = {}
    for batch_results in results_list:
        for result in batch_results:
            if validate_lqa_result(result):
                merged[result['id']] = result
    
    logger.info(f"合并后共 {len(merged)} 个有效结果")
    return merged


def process_global_lqa(
    api_client: APIClient,
    all_pairs: List[Dict[str, Any]],
    prompt_template: str,
    context: str = "",
    target_language: str = "zh_CN",
    source_language: str = "auto"
) -> Dict[str, Any]:
    """
    执行全局 LQA 深度审查
    
    Args:
        api_client: API 客户端
        all_pairs: 所有字幕对
        prompt_template: 全局 LQA 模板
        context: 项目背景
        target_language: 目标语言
        source_language: 原文语言
        
    Returns:
        全局 LQA 结果字典
    """
    # 格式化 Prompt
    system_prompt = format_prompt(prompt_template, context, target_language, source_language)
    user_prompt = json.dumps(all_pairs, ensure_ascii=False)
    
    try:
        # 调用 API
        response = api_client.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
            temperature=1.0
        )
        
        # 解析响应
        from core.utils.llm_utils import parse_json_from_response
        result = parse_json_from_response(response['text'])
        
        if result is None:
            raise json.JSONDecodeError("Failed to parse JSON", response['text'], 0)
            
        logger.info("全局 LQA 深度审查完成")
        return result
        
    except Exception as e:
        logger.error(f"全局 LQA 处理失败: {e}", exc_info=True)
        return {
            "global_score": 0,
            "global_summary": f"分析失败: {str(e)}",
            "consistency_issues": [],
            "major_errors": []
        }
