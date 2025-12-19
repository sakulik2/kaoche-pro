import os
import re
import logging
import pysubs2
from typing import List, Dict, Tuple, Optional
from core.utils.utils import detect_encoding

logger = logging.getLogger(__name__)

class SRTToolbox:
    """
    SRT 字幕工具箱核心逻辑类
    基于 pysubs2 库实现，并提供智能拆分、转换及清洗功能
    """
    
    def __init__(self):
        self.subs: Optional[pysubs2.SSAFile] = None
        
    def load_file(self, path: str, encoding: str = None) -> bool:
        """加载字幕文件，支持自动编码检测"""
        try:
            enc = encoding or detect_encoding(path)
            self.subs = pysubs2.load(path, encoding=enc)
            return True
        except Exception as e:
            logger.error(f"SRTToolbox 加载失败: {e}")
            return False

    def save_file(self, path: str, encoding: str = "utf-8"):
        """保存字幕文件"""
        if self.subs:
            self.subs.save(path, encoding=encoding)

    @staticmethod
    def concat_srts(file_paths: List[str]) -> pysubs2.SSAFile:
        """
        串联模式：将多个字幕文件按顺序首尾相接
        """
        combined = pysubs2.SSAFile()
        current_offset_ms = 0
        
        for path in file_paths:
            temp_subs = pysubs2.load(path, encoding=detect_encoding(path))
            
            # 将每个 event 偏移后加入总表
            for event in temp_subs.events:
                new_event = event.copy()
                new_event.start += current_offset_ms
                new_event.end += current_offset_ms
                combined.events.append(new_event)
                
            # 更新偏移量，取最后一个 event 的结束时间
            if temp_subs.events:
                current_offset_ms = combined.events[-1].end + 500 # 增加 0.5s 间隙
                
        return combined

    def split_bilingual_smart(self) -> Tuple[pysubs2.SSAFile, pysubs2.SSAFile]:
        """
        智控拆分：将双语字幕拆分为两个独立对象
        支持换行符拆分及正则模式识别（中英/中日等）
        """
        file_a = pysubs2.SSAFile() # 通常为母语/原文
        file_b = pysubs2.SSAFile() # 通常为外语/译文
        
        if not self.subs:
            return file_a, file_b

        # 预定义正则：识别中文字符
        zh_pattern = re.compile(r'[\u4e00-\u9fa5]')

        for event in self.subs.events:
            text = event.text.strip()
            # 1. 优先尝试换行符
            if '\n' in text or '\\N' in text:
                parts = text.replace('\\N', '\n').split('\n', 1)
                t1, t2 = parts[0].strip(), parts[1].strip()
            else:
                # 2. 正则智控拆分 (尝试识别中英边界)
                # 寻找中文和连续英文字符的交界处
                match = re.search(r'([\u4e00-\u9fa5]+)\s*([a-zA-Z\s,.\'!?]+)', text)
                if match:
                    t1, t2 = match.group(1).strip(), match.group(2).strip()
                else:
                    # 无法拆分，则放在同一个文件
                    t1, t2 = text, ""

            ev_a = event.copy()
            ev_a.text = t1
            file_a.events.append(ev_a)
            
            ev_b = event.copy()
            ev_b.text = t2
            file_b.events.append(ev_b)
            
        return file_a, file_b

    def merge_bilingual(self, other_subs: pysubs2.SSAFile):
        """双语合并：将另一个文件的文本拼接到当前文件"""
        if not self.subs or not other_subs: return
        
        count = min(len(self.subs.events), len(other_subs.events))
        for i in range(count):
            self.subs.events[i].text += "\\N" + other_subs.events[i].text

    def regroup_by_punctuation(self):
        """
        Whisper 语义重组：
        将全文按标点重组。解决 AI 生成字幕断句混乱的问题。
        通过字符比例线性插值还原时间轴。
        """
        if not self.subs or not self.subs.events: return
        
        # 1. 提取所有字符及其时间映射
        all_chars = []
        char_times = [] # [(start, end), ...]
        
        for ev in self.subs.events:
            text = ev.text.replace('\\N', ' ').replace('\n', ' ')
            if not text: continue
            
            duration = ev.end - ev.start
            char_count = len(text)
            for i, char in enumerate(text):
                # 简单的线性插值估算每个字符的时间
                c_start = ev.start + (i / char_count) * duration
                c_end = ev.start + ((i + 1) / char_count) * duration
                all_chars.append(char)
                char_times.append((c_start, c_end))
        
        full_text = "".join(all_chars)
        
        # 2. 根据标点切割句子
        # 匹配 。！？.!? 并保留标点
        sentences = re.split(r'([。！？.!?])', full_text)
        
        # 重新组合句子（split 后的列表是 [文本, 标点, 文本, 标点...]）
        new_events = []
        current_char_idx = 0
        
        combined_sentences = []
        for i in range(0, len(sentences)-1, 2):
            combined_sentences.append(sentences[i] + sentences[i+1])
        # 处理可能剩下的结尾
        if len(sentences) % 2 != 0 and sentences[-1]:
            combined_sentences.append(sentences[-1])
            
        for sent in combined_sentences:
            sent = sent.strip()
            if not sent: continue
            
            sent_len = len(sent)
            # 这句话在原始序列中的起始和截止索引
            # 注意：full_text 是由 all_chars 组成的，但可能存在空白字符处理差异
            # 这里我们通过内容匹配同步索引
            start_idx = full_text.find(sent, current_char_idx)
            if start_idx == -1: continue # 理论不应发生
            
            end_idx = start_idx + sent_len
            
            # 获取时间轴
            start_ms = char_times[start_idx][0]
            end_ms = char_times[end_idx-1][1]
            
            new_events.append(pysubs2.SSAEvent(start=int(start_ms), end=int(end_ms), text=sent))
            current_char_idx = end_idx
            
        if new_events:
            self.subs.events = new_events

    def txt_to_srt_smart(self, txt: str, interval_ms: int = 2000):
        """
        智能 TXT 转 SRT：按行读取，动态计算时长
        """
        self.subs = pysubs2.SSAFile()
        lines = [line.strip() for line in txt.split('\n') if line.strip()]
        
        current_ms = 0
        for line in lines:
            # 基础时长 + 每个字符增加 150ms
            duration = interval_ms + (len(line) * 150)
            
            event = pysubs2.SSAEvent(start=current_ms, end=current_ms + duration, text=line)
            self.subs.events.append(event)
            current_ms += duration + 200 # 200ms 间隔
            
    def shift_timeline(self, offset_ms: int):
        """时间批量偏移"""
        if self.subs:
            self.subs.shift(ms=offset_ms)

    def strip_timeline(self) -> str:
        """去除时间轴：提取所有文本并合并"""
        if not self.subs: return ""
        return "\n".join(ev.text for ev in self.subs.events)

    def crop_timeline(self, start_ms: int, end_ms: int):
        """裁剪时间轴，范围外删除，范围内重置起始点"""
        if not self.subs: return
        
        new_events = []
        for ev in self.subs.events:
            if ev.start >= start_ms and ev.end <= end_ms:
                new_ev = ev.copy()
                new_ev.start -= start_ms
                new_ev.end -= start_ms
                new_events.append(new_ev)
        self.subs.events = new_events

    def filter_text(self, mode: str = 'chinese_only'):
        """文本过滤：仅保留中文或英文"""
        if not self.subs: return
        
        pattern = re.compile(r'[\u4e00-\u9fa5]') if mode == 'chinese_only' else re.compile(r'[a-zA-Z]')
        
        for ev in self.subs.events:
            matches = pattern.findall(ev.text)
            ev.text = "".join(matches)

    def batch_replace(self, rep_dict: Dict[str, str]):
        """批量词汇替换"""
        if not self.subs: return
        for ev in self.subs.events:
            for k, v in rep_dict.items():
                ev.text = ev.text.replace(k, v)

    def fix_long_sentences(self, max_chars: int = 40):
        """智能断句：长句自动切分"""
        if not self.subs: return
        
        new_events = []
        for ev in self.subs.events:
            if len(ev.text) > max_chars:
                # 寻找分割点 (标点或空格)
                split_idx = -1
                for p in ["，", "。", "！", "？", ", ", ". ", "! ", "? "]:
                    idx = ev.text.find(p)
                    if 0 < idx < len(ev.text) - 1:
                        split_idx = idx + len(p)
                        break
                
                if split_idx == -1 and " " in ev.text:
                    split_idx = ev.text.find(" ", max_chars // 2)

                if split_idx != -1:
                    t1, t2 = ev.text[:split_idx].strip(), ev.text[split_idx:].strip()
                    mid_time = ev.start + (ev.end - ev.start) // 2
                    new_events.append(pysubs2.SSAEvent(start=ev.start, end=mid_time, text=t1))
                    new_events.append(pysubs2.SSAEvent(start=mid_time, end=ev.end, text=t2))
                    continue
            
            new_events.append(ev)
        self.subs.events = new_events

if __name__ == "__main__":
    # --- 字幕工具箱 (SRTToolbox) 使用示例 ---
    toolbox = SRTToolbox()
    
    # 1. 智能 TXT 转 SRT
    txt_data = "你好，这是第一句。\n这是一句非常长的字幕，我们需要通过智能断句功能来处理它，看看效果如何。"
    print(">>> 执行 TXT 转 SRT (智能时长分配)...")
    toolbox.txt_to_srt_smart(txt_data, interval_ms=1000)
    
    # 2. 智能断句
    print(">>> 执行智能断句 (Max 20 chars)...")
    toolbox.fix_long_sentences(max_chars=20)
    
    # 3. 时间轴偏移 (前进 500ms)
    print(">>> 时间轴整体后移 500ms...")
    toolbox.shift_timeline(500)
    
    # 4. 获取纯文本摘要
    print(">>> 提取纯文本内容:")
    print(toolbox.strip_timeline())
    
    # 5. 保存
    # toolbox.save_file("demo_output.srt")
    print("\n[示例完成] 核心逻辑正常运作。")
