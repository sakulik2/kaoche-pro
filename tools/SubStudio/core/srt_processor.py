import re
import logging

logger = logging.getLogger(__name__)

class SRTProcessor:
    """
    高级字幕后处理器 (SRTProcessor)
    参考实施方案，提供更智能的清洗、分段与格式化逻辑。
    """
    
    # 常见的幻听/噪声模式 (Whisper 极其容易在静默期生成的无效文本)
    HALLUCINATION_PATTERNS = [
        r"\[.*?\]",               # [Music], [Applause], [Silence]
        r"\(.*?\)",               # (text in parentheses)
        r"(\*+)",                 # ***
        r"♪",                     # 单个或多个音符
        r"谢谢观看",   
        r"请订阅",                
        r"字幕由.*提供",          
        r"Thank you for watching",
        r"Thanks for watching",
        r"Please subscribe",
        r"Please like and subscribe",
        r"Subtitles by",
        r"Subtitles translated by",
        r"Subtitles managed by",
        r"See you in the next one",
        r"See you in the next video",
        r"I hope you enjoyed this video",
        r"Amara.org",
        r"OpenSubtitles.org",
        r"www\..*?\.(com|org|net)", # 常见的网址
    ]
    
    @staticmethod
    def clean_text(text):
        """清洗文本中的无效标记和幻觉"""
        for pattern in SRTProcessor.HALLUCINATION_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        # 去除多余空格和首尾标点（如果是整段被删除了，返回空）
        return text.strip()

    @staticmethod
    def split_smartly(text, lang="zh", max_len=30):
        """
        智能换行/切分。
        优先在标点符号处切分。
        """
        if len(text) <= max_len:
            return text
            
        # 英文标点与中文标点
        punctuations = [",", ".", "!", "?", ";", "，", "。", "！", "？", "；", " "]
        
        # 如果已经有换行符，不再处理
        if "\n" in text:
            return text
            
        # 寻找最接近中间的切分点
        mid = len(text) // 2
        best_pos = -1
        min_dist = float('inf')
        
        for i, char in enumerate(text):
            if char in punctuations:
                # 计算距离中点的距离
                dist = abs(i - mid)
                if dist < min_dist:
                    min_dist = dist
                    best_pos = i
                    
        # 如果找到了合适的标点切分点
        if best_pos != -1 and min_dist < max_len // 3:
            # 在标点后添加换行
            return text[:best_pos+1].strip() + "\n" + text[best_pos+1:].strip()
        
        # 兜底方案：强制中点对半开
        return text[:mid].strip() + "\n" + text[mid:].strip()

    @staticmethod
    def global_regroup_by_punctuation(segments):
        """
        全局语义重组 (参考 SRTToolbox 逻辑)：
        将所有片段合并为一整个字符流，然后依据末尾标点重新切分，以解决 AI 断句过于碎片化的问题。
        """
        if not segments:
            return []
            
        # 1. 建立全局字符时间映射
        all_chars = []
        char_times = [] # [(start, end), ...]
        
        for seg in segments:
            text = seg["text"].replace('\n', ' ').strip()
            if not text: continue
            
            start = seg["start"]
            end = seg["end"]
            duration = end - start
            char_count = len(text)
            
            text = seg["text"].replace('\n', ' ').strip()
            if not text: continue
            
            start = seg["start"]
            end = seg["end"]
            duration = end - start
            char_count = len(text)
            
            # --- [优化时间提取] ---
            # 优先使用字符级对齐 (WhisperX return_char_alignments=True)
            if "chars" in seg and seg["chars"]:
                c_data = seg["chars"]
                c_idx = 0
                
                for char in text:
                    # 尝试匹配
                    current_c_obj = None
                    if c_idx < len(c_data):
                        # 宽松匹配：忽略大小写，或者完全一致
                        if c_data[c_idx].get("char") == char:
                            current_c_obj = c_data[c_idx]
                            c_idx += 1
                    
                    if current_c_obj and "start" in current_c_obj and "end" in current_c_obj:
                        all_chars.append(char)
                        char_times.append((current_c_obj["start"], current_c_obj["end"]))
                    else:
                        # 标点符号或未对齐字符：插值填充
                        # 找上一个有时间的和下一个有时间的
                        prev_end = char_times[-1][1] if char_times else start
                        # 向后搜索最近的一个有时间的字符
                        next_start = end
                        scan_k = c_idx
                        while scan_k < len(c_data):
                            if "start" in c_data[scan_k]:
                                next_start = c_data[scan_k]["start"]
                                break
                            scan_k += 1
                        
                        # 简单平均分配
                        all_chars.append(char)
                        # 暂且给一个极小宽度，或者平铺
                        char_times.append((prev_end, next_start)) 
                        # 追加操作隐含更新了用于下次循环的 prev_end
            
            # 其次使用单词级对齐 (WhisperX 标准模式)
            elif "words" in seg and seg["words"]:
                w_data = seg["words"]
                # 这是一个简化的映射逻辑：将 text 里的字符分配给 words
                # 实际 text 可能包含标点，而 words[i]['word'] 可能包含也可能不包含
                # 简单粗暴策略：直接按时间段均匀插值字符位置
                
                # 我们构建一个临时的 "chars_with_time" 列表 (基于 words)
                # 将每个 word 的时间均分给它的字符
                temp_char_buffer = [] # [(char, s, e)]
                
                for w in w_data:
                    w_text = w.get("word", "")
                    w_start = w.get("start", start)
                    w_end = w.get("end", end)
                    w_dur = w_end - w_start
                    w_len = len(w_text)
                    if w_len == 0: continue
                    
                    for k, wc in enumerate(w_text):
                        ws = w_start + (k / w_len) * w_dur
                        we = w_start + ((k + 1) / w_len) * w_dur
                        temp_char_buffer.append( (wc, ws, we) )
                        
                # 这里的 temp_char_buffer 是基于 words 的
                # seg["text"] 是基于整句的 (包含额外标点空格)
                
                # 如果缺少字符对齐信息，回退到标准线性插值以保持稳定性
                for i, char in enumerate(text):
                    c_start = start + (i / char_count) * duration
                    c_end = start + ((i + 1) / char_count) * duration
                    all_chars.append(char)
                    char_times.append((c_start, c_end))
                    
            else:
                # 线性插值估算每个字符的时间轴 (兜底方案)
                for i, char in enumerate(text):
                    c_start = start + (i / char_count) * duration
                    c_end = start + ((i + 1) / char_count) * duration
                    all_chars.append(char)
                    char_times.append((c_start, c_end))
        
        if not all_chars:
            return segments
            
        full_text = "".join(all_chars)
        
        # 2. 根据末尾标点切割 (。！？.!? \n)
        # 强化标点符号识别 (增加更多语言的终结符)
        terminal_punctuations = r'([。！？\.!\?；;?])' # 增加逗号和分号作为次级切割点
        sentences = re.split(terminal_punctuations, full_text)
        
        # 重新组合：[文本, 标点, 文本, 标点...] -> [文本+标点, ...]
        combined_list = []
        for i in range(0, len(sentences)-1, 2):
            s = (sentences[i] + sentences[i+1]).strip()
            if s: combined_list.append(s)
        if len(sentences) % 2 != 0 and sentences[-1].strip():
            combined_list.append(sentences[-1].strip())
            
        # --- [兜底] ---
        # 如果模型完全没给标点，combined_list 可能会只有一个超长的句子。
        # 我们需要强制进行二次切分。
        if len(combined_list) == 1 and len(combined_list[0]) > 25:
            text_to_split = combined_list[0]
            fallback_list = []
            chunk_size = 15 # 无标点时，每 15-20 字强行断句
            for i in range(0, len(text_to_split), chunk_size):
                chunk = text_to_split[i:i+chunk_size].strip()
                if chunk: fallback_list.append(chunk)
            combined_list = fallback_list
            
        # 3. 还原时间轴并生成新片段
        new_segments = []
        current_char_idx = 0
        
        for sent in combined_list:
            # 找到这句话在全局流中的位置 (精确查找，防止索引漂移)
            start_idx = full_text.find(sent, current_char_idx)
            if start_idx == -1: 
                # 容错：如果精确查找失败（罕见），使用滑动窗口逻辑或跳过
                continue
            
            end_idx = start_idx + len(sent)
            
            # 提取起止时间
            s_start = char_times[start_idx][0]
            s_end = char_times[end_idx-1][1]
            
            new_segments.append({
                "start": s_start,
                "end": s_end,
                "text": sent
            })
            current_char_idx = end_idx
            
        return new_segments if new_segments else segments

    @staticmethod
    def process_segments(segments, lang="zh", max_chars=38, min_gap_ms=80, min_duration_ms=500):
        """
        全量处理流水线
        """
        if not segments:
            return []
            
        # 1. 基础清理
        cleaned = []
        for seg in segments:
            text = SRTProcessor.clean_text(seg.get("text", ""))
            if text:
                cleaned.append({"start": seg["start"], "end": seg["end"], "text": text})
            
        if not cleaned:
            return []

        # 2. 全局语义重组 (解决 Whisper 碎片化问题)
        segments_regrouped = SRTProcessor.global_regroup_by_punctuation(cleaned)

        # 3. 闭合间隙与重叠修正
        for i in range(len(segments_regrouped) - 1):
            curr_end = segments_regrouped[i]["end"] * 1000
            next_start = segments_regrouped[i+1]["start"] * 1000
            gap = next_start - curr_end
            if 0 < gap < min_gap_ms:
                segments_regrouped[i]["end"] = segments_regrouped[i+1]["start"]
            if segments_regrouped[i]["end"] > segments_regrouped[i+1]["start"]:
                segments_regrouped[i]["end"] = segments_regrouped[i+1]["start"]

        # 4. 强制最小持续时间
        for i in range(len(segments_regrouped)):
            dur = (segments_regrouped[i]["end"] - segments_regrouped[i]["start"]) * 1000
            if dur < min_duration_ms:
                segments_regrouped[i]["end"] = segments_regrouped[i]["start"] + (min_duration_ms / 1000.0)

        # 5. 句内智能换行 (单行超过限制时加 \n)
        final = []
        for seg in segments_regrouped:
            seg["text"] = SRTProcessor.split_smartly(seg["text"], lang=lang, max_len=max_chars)
            final.append(seg)

        return final
