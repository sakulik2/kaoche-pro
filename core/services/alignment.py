"""
字幕对齐算法模块
基于时间轴的智能对齐
"""

from typing import List, Dict, Tuple
import logging

from .lqa_processor import load_prompt_template

logger = logging.getLogger(__name__)


def align_subtitles(source_data: List[Dict], target_data: List[Dict], 
                   anchor_mode: str = 'source') -> List[Tuple[Dict, Dict]]:
    """
    基于时间轴的智能对齐算法
    
    Args:
        source_data: 原文字幕数据 (含 start, end, text)
        target_data: 译文字幕数据 (含 start, end, text)
        anchor_mode: 对齐模式
            - 'source': 以原文为轴，每行原文匹配一个或多个译文（默认）
            - 'target': 以译文为轴，每行译文匹配一个或多个原文
        
    Returns:
        对齐后的 [(source_dict, target_dict), ...] 列表，保留完整的字典对象（包含时间戳）
    """
    if anchor_mode not in ['source', 'target', 'auto']:
        raise ValueError(f"Invalid anchor_mode: {anchor_mode}. Must be 'source', 'target', or 'auto'.")
    
    if anchor_mode == 'auto':
        anchor_mode = 'source'  # auto默认使用source
    
    if anchor_mode == 'source':
        return _align_source_anchored(source_data, target_data)
    else:  # anchor_mode == 'target'
        return _align_target_anchored(source_data, target_data)


def _align_source_anchored(source_data: List[Dict], target_data: List[Dict]) -> List[Tuple[Dict, Dict]]:
    """
    以原文为轴的严格对齐算法（新版）
    
    规则:
    1. 时间上完全包含 = 匹配
    2. 错开了就留空，不强行配对
    3. 分段对齐，找到下一个能配对的重新开始
    
    Returns:
        List[Tuple[Dict, Dict]]: 包含完整字典对象的对齐结果
    """
    aligned = []
    used_target_indices = set()
    
    for src_idx, s in enumerate(source_data):
        s_start = s['start']
        s_end = s['end']
        
        # 寻找时间上匹配的译文
        matched_targets = []
        
        for t_idx, t in enumerate(target_data):
            if t_idx in used_target_indices:
                continue
            
            t_start = t['start']
            t_end = t['end']
            
            # 检查包含关系
            # 情况1: 译文完全包含在原文时间内
            if t_start >= s_start and t_end <= s_end:
                matched_targets.append((t_idx, t))
            # 情况2: 原文完全包含在译文时间内  
            elif s_start >= t_start and s_end <= t_end:
                matched_targets.append((t_idx, t))
            # 情况3: 有显著重叠（至少50%）
            else:
                overlap_start = max(s_start, t_start)
                overlap_end = min(s_end, t_end)
                overlap_duration = overlap_end - overlap_start
                
                if overlap_duration > 0:
                    s_duration = s_end - s_start
                    t_duration = t_end - t_start
                    
                    # 重叠占原文的比例
                    s_overlap_ratio = overlap_duration / s_duration if s_duration > 0 else 0
                    # 重叠占译文的比例  
                    t_overlap_ratio = overlap_duration / t_duration if t_duration > 0 else 0
                    
                    # 如果重叠占任一方的50%以上，认为是匹配
                    if s_overlap_ratio >= 0.5 or t_overlap_ratio >= 0.5:
                        matched_targets.append((t_idx, t))
        
        if matched_targets:
            # 按索引排序
            matched_targets.sort(key=lambda x: x[0])
            
            # 合并多个译文的文本
            combined_text = "\n".join([m[1]['text'] for m in matched_targets])
            
            # 创建合并后的target字典（使用第一个译文的时间，文本合并）
            merged_target = matched_targets[0][1].copy()
            merged_target['text'] = combined_text
            # 如果有多个译文，使用最晚的结束时间
            if len(matched_targets) > 1:
                merged_target['end'] = max([m[1]['end'] for m in matched_targets])
            
            aligned.append((s, merged_target))
            
            # 标记已使用
            for m in matched_targets:
                used_target_indices.add(m[0])
        else:
            # 没有匹配，创建空译文字典
            empty_target = {'start': s['start'], 'end': s['end'], 'text': ''}
            aligned.append((s, empty_target))
            
    logger.info(f"[原文为轴] 对齐完成: {len(aligned)} 行原文, {len(used_target_indices)} 行译文被匹配")
    
    unmatched_count = len(target_data) - len(used_target_indices)
    if unmatched_count > 0:
        logger.warning(f"有 {unmatched_count} 行译文未被匹配到原文")
    
    return aligned


def _align_target_anchored(source_data: List[Dict], target_data: List[Dict]) -> List[Tuple[Dict, Dict]]:
    """
    以译文为轴的严格对齐算法（新版）
    
    规则:
    1. 时间上完全包含 = 匹配
    2. 错开了就留空，不强行配对
    3. 分段对齐，找到下一个能配对的重新开始
    4. 允许多个译文匹配同一个原文（原文可重用）
    
    Returns:
        List[Tuple[Dict, Dict]]: 包含完整字典对象的对齐结果
    """
    aligned = []
    
    for t_idx, t in enumerate(target_data):
        t_start = t['start']
        t_end = t['end']
        
        # 寻找时间上匹配的原文
        matched_sources = []
        
        for s_idx, s in enumerate(source_data):
            s_start = s['start']
            s_end = s['end']
            
            # 检查包含关系
            # 情况1: 原文完全包含在译文时间内
            if s_start >= t_start and s_end <= t_end:
                matched_sources.append((s_idx, s))
            # 情况2: 译文完全包含在原文时间内
            elif t_start >= s_start and t_end <= s_end:
                matched_sources.append((s_idx, s))
            # 情况3: 有显著重叠（至少50%）
            else:
                overlap_start = max(s_start, t_start)
                overlap_end = min(s_end, t_end)
                overlap_duration = overlap_end - overlap_start
                
                if overlap_duration > 0:
                    s_duration = s_end - s_start
                    t_duration = t_end - t_start
                    
                    s_overlap_ratio = overlap_duration / s_duration if s_duration > 0 else 0
                    t_overlap_ratio = overlap_duration / t_duration if t_duration > 0 else 0
                    
                    if s_overlap_ratio >= 0.5 or t_overlap_ratio >= 0.5:
                        matched_sources.append((s_idx, s))
        
        if matched_sources:
            # 按索引排序
            matched_sources.sort(key=lambda x: x[0])
            
            # 合并多个原文的文本
            combined_text = "\n".join([m[1]['text'] for m in matched_sources])
            
            # 创建合并后的source字典
            merged_source = matched_sources[0][1].copy()
            merged_source['text'] = combined_text
            if len(matched_sources) > 1:
                merged_source['end'] = max([m[1]['end'] for m in matched_sources])
            
            aligned.append((merged_source, t))
        else:
            # 没有匹配，创建空原文字典
            empty_source = {'start': t['start'], 'end': t['end'], 'text': ''}
            aligned.append((empty_source, t))
    
    # 后处理：合并连续的相同原文
    merged = _merge_consecutive_sources(aligned)
    
    # 统计信息
    source_matches = sum(1 for src, _ in merged if src.get('text', ''))
    logger.info(f"[译文为轴] 对齐完成: {len(merged)} 行（合并后）, {source_matches} 行有原文匹配")
    
    return merged


def _merge_consecutive_sources(aligned: List[Tuple[Dict, Dict]]) -> List[Tuple[Dict, Dict]]:
    """
    合并连续的相同原文，将其对应的译文合并
    
    例如：
    [({'text': 'EN1', ...}, {'text': 'CN1', ...}), 
     ({'text': 'EN1', ...}, {'text': 'CN2', ...}), 
     ({'text': 'EN2', ...}, {'text': 'CN3', ...})]
    变成：
    [({'text': 'EN1', ...}, {'text': 'CN1\nCN2', ...}), 
     ({'text': 'EN2', ...}, {'text': 'CN3', ...})]
    """
    if not aligned:
        return aligned
    
    merged = []
    i = 0
    
    while i < len(aligned):
        current_src, current_tgt = aligned[i]
        current_src_text = current_src.get('text', '') if isinstance(current_src, dict) else str(current_src)
        
        # 收集所有连续的相同原文
        targets = [current_tgt]
        j = i + 1
        
        while j < len(aligned):
            next_src = aligned[j][0]
            next_src_text = next_src.get('text', '') if isinstance(next_src, dict) else str(next_src)
            
            if next_src_text == current_src_text:
                targets.append(aligned[j][1])
                j += 1
            else:
                break
        
        # 合并译文
        if len(targets) > 1:
            # 合并多个译文的文本
            merged_text = "\n".join([t.get('text', '') if isinstance(t, dict) else str(t) for t in targets])
            
            # 创建合并后的target字典
            merged_target = targets[0].copy() if isinstance(targets[0], dict) else {'text': str(targets[0])}
            merged_target['text'] = merged_text
            # 使用最晚的结束时间
            if isinstance(targets[-1], dict) and 'end' in targets[-1]:
                merged_target['end'] = targets[-1]['end']
            
            merged.append((current_src, merged_target))
        else:
            # 只有一个目标，直接添加
            merged.append((current_src, current_tgt))
        
        # 跳到下一个不同的原文
        i = j
    
    return merged


def simple_align_by_line_count(source_lines: List[str], target_lines: List[str]) -> List[Tuple[str, str]]:
    """
    简单的按行数对齐（用于无时间轴的纯文本）
    
    Args:
        source_lines: 原文行列表
        target_lines: 译文行列表
        
    Returns:
        对齐后的 [(source, target), ...] 列表
    """
    max_len = max(len(source_lines), len(target_lines))
    aligned = []
    
    for i in range(max_len):
        source = source_lines[i] if i < len(source_lines) else ""
        target = target_lines[i] if i < len(target_lines) else ""
        aligned.append((source, target))
    
    logger.info(f"按行数简单对齐完成: {len(aligned)} 行")
    return aligned


def align_subtitles_with_llm(source_data: List[Dict], target_data: List[Dict], 
                             api_client, anchor_mode: str = 'source') -> List[Tuple[str, str]]:
    """
    使用 LLM 进行智能对齐（基于语义而非时间轴）
    
    适用场景：
    1. 字幕时间轴不准确
    2. 纯文本对齐（无时间信息）
    3. 需要更智能的语义匹配
    
    Args:
        source_data: 原文字幕列表（可以是带时间轴的dict或纯文本list）
        target_data: 译文字幕列表
        api_client: API客户端实例
        anchor_mode: 对齐模式 ('source' 或 'target')
        
    Returns:
        对齐后的 [(source_text, target_text), ...] 列表
    """
    import json
    
    # 提取文本内容
    if isinstance(source_data[0], dict):
        source_texts = [item['text'] for item in source_data]
    else:
        source_texts = source_data
    
    if isinstance(target_data[0], dict):
        target_texts = [item['text'] for item in target_data]
    else:
        target_texts = target_data
    
    logger.info(f"开始 LLM 对齐: {len(source_texts)} 原文, {len(target_texts)} 译文")
    
    # 读取prompt模板
    system_prompt = load_prompt_template(".alignment.txt")
    if not system_prompt:
        # 使用默认prompt
        system_prompt = """你是一个专业的字幕对齐助手。根据语义匹配原文和译文。
输出JSON数组格式：[{"source": "...", "target": "..."}]"""
    
    user_prompt = f"""请对齐以下字幕：

原文字幕 ({len(source_texts)} 行)：
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(source_texts)])}

译文字幕 ({len(target_texts)} 行)：
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(target_texts)])}

对齐模式: {"以原文为基准" if anchor_mode == 'source' else "以译文为基准"}

请返回对齐后的 JSON 数组。"""

    try:
        # 调用 LLM
        response = api_client.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True
        )
        
        # 解析响应
        from .llm_utils import parse_json_from_response
        
        if isinstance(response, dict) and 'content' in response:
            content = response['content']
        else:
            content = str(response)
            
        aligned_data = parse_json_from_response(content)
        if aligned_data is None:
             raise ValueError("无法从 LLM 响应中提取 JSON")
        
        # 转换为标准格式
        aligned = []
        for item in aligned_data:
            source = item.get('source', '')
            target = item.get('target', '')
            aligned.append((source, target))
        
        logger.info(f"LLM 对齐完成: {len(aligned)} 对")
        return aligned
        
    except Exception as e:
        logger.error(f"LLM 对齐失败: {str(e)}")
        logger.warning("回退到简单的按行对齐")
        
        # 回退到简单对齐
        return simple_align_by_line_count(source_texts, target_texts)


def fill_alignment_gaps(aligned: List[Tuple[str, str]], 
                       source_data: List[Dict], 
                       target_data: List[Dict],
                       api_client,
                       auto_fill: bool = True,
                       max_retries: int = 3,
                       batch_size: int = 10) -> List[Tuple[str, str]]:
    """
    自动填补对齐中的空缺（带上下文和重试机制）
    
    检测时间轴对齐后的空行（未匹配项），使用 LLM 进行语义匹配填补
    
    工作流程：
    1. 提取未匹配的字幕
    2. 将已匹配的部分作为上下文发给LLM
    3. LLM返回填补结果
    4. 验证是否还有空行
    5. 如有空行且未达重试次数，返回步骤2
    
    Args:
        aligned: 时间轴对齐的结果
        source_data: 原始原文数据
        target_data: 原始译文数据
        api_client: API客户端实例
        auto_fill: 是否自动填补空缺
        max_retries: 最大重试次数
        
    Returns:
        填补后的对齐结果
    """
    if not auto_fill:
        return aligned
    
    current_aligned = aligned
    retry_count = 0
    
    while retry_count < max_retries:
        # 统计空行
        empty_count = sum(1 for src, tgt in current_aligned if not src or not tgt)
        
        if empty_count == 0:
            logger.info(f"没有空缺，填补完成（重试{retry_count}次）")
            return current_aligned
        
        logger.info(f"检测到 {empty_count} 个空缺（第{retry_count+1}次尝试）")
        
        try:
            # 提取未匹配的原文和译文
            unmatched_sources = []
            unmatched_targets = []
            
            # 收集所有已匹配的文本
            matched_source_texts = set(src for src, _ in current_aligned if src)
            matched_target_texts = set(tgt for _, tgt in current_aligned if tgt)
            
            # 找出未匹配的
            for item in source_data:
                if item['text'] not in matched_source_texts:
                    unmatched_sources.append(item['text'])
            
            for item in target_data:
                if item['text'] not in matched_target_texts:
                    unmatched_targets.append(item['text'])
            
            if not unmatched_sources and not unmatched_targets:
                logger.info("没有未匹配项，填补完成")
                return current_aligned
            
            # 准备上下文：提取已匹配的部分作为参考
            context_pairs = [(src, tgt) for src, tgt in current_aligned if src and tgt]

            # 分批处理未匹配项
            llm_aligned = []
            
            # 确定循环次数（以较长的列表为准）
            num_unmatched = max(len(unmatched_sources), len(unmatched_targets))
            
            for i in range(0, num_unmatched, batch_size):
                batch_sources = unmatched_sources[i : i + batch_size]
                batch_targets = unmatched_targets[i : i + batch_size]
                
                logger.info(f"正在处理第 {i//batch_size + 1} 批次对齐 ({len(batch_sources)} 原文, {len(batch_targets)} 译文)")
                
                # 使用 LLM 对齐批次（带上下文）
                batch_result = _align_with_context(
                    batch_sources,
                    batch_targets,
                    context_pairs,
                    api_client
                )
                llm_aligned.extend(batch_result)
            
            # 合并结果：填补原对齐结果中的空缺
            result = []
            llm_index = 0
            
            for src, tgt in current_aligned:
                if not src and not tgt:
                    # 双空，跳过
                    continue
                elif not src:
                    # 原文为空，尝试从LLM结果填补
                    if llm_index < len(llm_aligned):
                        llm_src, _ = llm_aligned[llm_index]
                        result.append((llm_src, tgt))
                        llm_index += 1
                    else:
                        result.append((src, tgt))
                elif not tgt:
                    # 译文为空，尝试从LLM结果填补
                    if llm_index < len(llm_aligned):
                        _, llm_tgt = llm_aligned[llm_index]
                        result.append((src, llm_tgt))
                        llm_index += 1
                    else:
                        result.append((src, tgt))
                else:
                    # 双非空，保持原样
                    result.append((src, tgt))
            
            # 添加剩余的LLM结果
            while llm_index < len(llm_aligned):
                result.append(llm_aligned[llm_index])
                llm_index += 1
            
            # 更新当前对齐结果
            current_aligned = result
            retry_count += 1
            
            logger.info(f"第{retry_count}次填补完成: {len(current_aligned)} 对")
            
        except Exception as e:
            logger.error(f"LLM 填补失败（重试{retry_count}次）: {str(e)}")
            return current_aligned
    
    # 达到最大重试次数
    remaining_empty = sum(1 for src, tgt in current_aligned if not src or not tgt)
    if remaining_empty > 0:
        logger.warning(f"达到最大重试次数({max_retries})，仍有{remaining_empty}个空缺")
    
    return current_aligned


def _align_with_context(unmatched_sources: List[str],
                       unmatched_targets: List[str],
                       context_pairs: List[Tuple[str, str]],
                       api_client) -> List[Tuple[str, str]]:
    """
    使用LLM对齐，带上下文参考
    
    Args:
        unmatched_sources: 未匹配的原文列表
        unmatched_targets: 未匹配的译文列表
        context_pairs: 已匹配的对齐对作为上下文
        api_client: API客户端
        
    Returns:
        对齐结果
    """
    import json
    
    # 读取prompt模板
    system_prompt = load_prompt_template(".alignment.txt")
    if not system_prompt:
        system_prompt = """你是专业的字幕对齐助手。根据语义匹配原文和译文。
输出JSON数组格式：[{"source": "...", "target": "..."}]"""
    
    # 构建用户prompt，包含上下文
    user_prompt = f"""请对齐以下未匹配的字幕。

**已匹配的参考上下文**（帮助你理解内容和风格）：
前10行和后10行的已匹配内容：
"""
    
    # 提取前10行和后10行作为上下文（总共最多20行）
    context_window_size = 10
    total_context = min(len(context_pairs), context_window_size * 2)
    
    # 取前10行
    for i, (src, tgt) in enumerate(context_pairs[:context_window_size]):
        user_prompt += f"{i+1}. 原文: {src[:50]}{'...' if len(src) > 50 else ''} → 译文: {tgt[:50]}{'...' if len(tgt) > 50 else ''}\n"
    
    if len(context_pairs) > context_window_size:
        user_prompt += "...\n"
        # 取后10行
        start_idx = max(context_window_size, len(context_pairs) - context_window_size)
        for i, (src, tgt) in enumerate(context_pairs[start_idx:], start=start_idx):
            user_prompt += f"{i+1}. 原文: {src[:50]}{'...' if len(src) > 50 else ''} → 译文: {tgt[:50]}{'...' if len(tgt) > 50 else ''}\n"
    
    user_prompt += f"""

**需要你匹配的未匹配字幕**：

未匹配原文 ({len(unmatched_sources)} 行)：
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(unmatched_sources)])}

未匹配译文 ({len(unmatched_targets)} 行)：
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(unmatched_targets)])}

请根据上下文参考和语义相似度，返回对齐后的 JSON 数组。
格式：[{{"source": "...", "target": "..."}}]
"""

    try:
        # 调用 LLM
        response = api_client.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True
        )
        
        # 解析响应
        from .llm_utils import parse_json_from_response
        
        if isinstance(response, dict) and 'content' in response:
            content = response['content']
        else:
            content = str(response)
            
        aligned_data = parse_json_from_response(content)
        if aligned_data is None:
             raise ValueError("无法从 LLM 响应中提取 JSON")
        
        # 转换为标准格式
        aligned = []
        for item in aligned_data:
            source = item.get('source', '')
            target = item.get('target', '')
            aligned.append((source, target))
        
        logger.info(f"LLM 返回 {len(aligned)} 对对齐结果")
        return aligned
        
    except Exception as e:
        logger.error(f"LLM 对齐失败: {str(e)}")
        # 回退到简单配对
        return simple_align_by_line_count(unmatched_sources, unmatched_targets)
