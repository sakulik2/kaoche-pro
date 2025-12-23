
import os
import logging
import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QThread
import sherpa_onnx
import whisperx # 一些重利用
from pysubs2 import SSAFile, SSAEvent
import re

import torch
try:
    import langdetect
except ImportError:
    langdetect = None
import gc

logger = logging.getLogger(__name__)

class SherpaTranscriptionWorker(QThread):
    progress = pyqtSignal(str) # 进度文本
    progress_percent = pyqtSignal(int) # 0-100
    finished = pyqtSignal(bool, object)

    def __init__(self, model_path, audio_path, models_root, device="cpu", language=None, punct_model_path=None, align=True):
        super().__init__()
        self.model_path = model_path
        self.audio_path = audio_path
        self.models_root = models_root
        self.device = device
        self.language = language
        self.punct_model_path = punct_model_path
        self.align = align
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _find_model_files(self, model_dir):
        """自动检测目录下的 encoder, decoder, joiner, tokens 文件"""
        files = os.listdir(model_dir)
        config = {}
        
        # 辅助函数：按子串查找文件
        def find_one(substrings, extension=".onnx"):
            if isinstance(substrings, str): substrings = [substrings]
            for f in files:
                if f.endswith(extension):
                    for sub in substrings:
                        if sub in f: return os.path.join(model_dir, f)
            return None

        config['tokens'] = os.path.join(model_dir, "tokens.txt")
        config['encoder'] = find_one(["encoder"])
        config['decoder'] = find_one(["decoder"])
        config['joiner'] = find_one(["joiner"])
        
        return config

    def run(self):
        try:
            self.progress.emit("初始化 Sherpa-ONNX 引擎 (CPU)...")
            self.progress_percent.emit(5)
            
            # [Windows CUDA 兼容性修复]
            # Windows 下 onnxruntime-gpu 经常无法找到 PyTorch 附带的 zlibwapi.dll 或 cuDNN。
            # 这里显式将 torch/lib 加入 DLL 搜索路径。
            if os.name == 'nt' and "cuda" in self.device:
                try:
                    import torch
                    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')
                    if os.path.exists(torch_lib_path):
                        # 方法 1: Python 3.8+ 安全 DLL 加载
                        if hasattr(os, 'add_dll_directory'):
                            os.add_dll_directory(torch_lib_path)
                            logger.info(f"Added torch/lib to DLL directory: {torch_lib_path}")
                        # 方法 2: 传统 PATH 修改 (双重保险)
                        os.environ['PATH'] = torch_lib_path + os.pathsep + os.environ['PATH']
                except Exception as dll_e:
                    logger.warning(f"Failed to inject torch lib path: {dll_e}")

            # 1. 配置 Recognizer
            files = self._find_model_files(self.model_path)
            if not all(files.values()):
                missing = [k for k, v in files.items() if not v]
                raise FileNotFoundError(f"Incomplete model files in {self.model_path}. Missing: {missing}")

            logger.info(f"Loading Sherpa model from {self.model_path}")
            
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                tokens=files['tokens'],
                encoder=files['encoder'],
                decoder=files['decoder'],
                joiner=files['joiner'],
                num_threads=1, # 减少线程数以降低内存占用 (避免分配错误)
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                model_type="nemo_transducer", # 显式设置为 Parakeet TDT 模型以修复元数据错误
                provider="cuda" if "cuda" in self.device else "cpu"
            )
        except Exception as e:
            if "cuda" in self.device:
                logger.warning(f"Sherpa CUDA init failed: {e}. Fallback to CPU.")
                recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    tokens=files['tokens'],
                    encoder=files['encoder'],
                    decoder=files['decoder'],
                    joiner=files['joiner'],
                    num_threads=1,
                    sample_rate=16000,
                    feature_dim=80,
                    decoding_method="greedy_search",
                    model_type="nemo_transducer",
                    provider="cpu"
                )
            else:
                raise e
            
            if self._is_cancelled: return

            # 2. 加载音频
            self.progress.emit("正在读取音频 (Decoding)...")
            self.progress_percent.emit(10)
            
            # 使用 whisperx (ffmpeg) 加载音频，确保支持视频文件
            logger.info(f"Loading audio from {self.audio_path}...")
            audio = whisperx.load_audio(self.audio_path)
            duration = len(audio) / 16000.0
            logger.info(f"Audio loaded. Shape: {audio.shape}, Duration: {duration:.2f}s, Dtype: {audio.dtype}")
            
            # 确保音频为单声道
            if len(audio.shape) > 1:
                logger.info("Converting stereo to mono...")
                audio = audio.mean(axis=1) # 简单的混合降维 (如果 whisperx 返回了立体声)
                
            # 3. VAD 分割 (解决长音频 OOM 问题)
            self.progress.emit("正在进行 VAD 语音活动检测...")
            self.progress_percent.emit(15)
            
            # 稳健导入 VAD
            try:
                # 尝试从 whisperx 内部导入
                from whisperx.vads.pyannote import load_vad_model
            except ImportError:
                logger.error("Could not import load_vad_model from whisperx.vads.pyannote. Please check whisperx installation.")
                raise

            # Load VAD model (always CPU to be safe/simple, or match device)
            
            # [CRITICAL] PyTorch 2.6+ ... (Monkeypatch kept here) ...
            
            # ... (VAD model loading code is here, no need to touch) ...
            
            # 1.5 Load Punctuation Model (if available)
            punct_model = None
            if self.punct_model_path:
                try:
                    logger.info(f"Loading Punctuation model from {self.punct_model_path}")
                    # 标点模型通常包含 model.onnx (CT-Transformer 架构)
                    # 我们假定模型目录结构符合标准 sherpa-onnx 格式
                    # 并配置 OfflinePunctuation 使用 ct_transformer 模型
                    
                    punct_config = sherpa_onnx.OfflinePunctuationConfig(
                        model=sherpa_onnx.OfflinePunctuationModelConfig(
                            ct_transformer=os.path.join(self.punct_model_path, "model.onnx")
                        )
                    )
                    punct_model = sherpa_onnx.OfflinePunctuation(punct_config)
                    logger.info("Punctuation model loaded.")
                except Exception as e:
                    logger.error(f"Failed to load punctuation model: {e}")
                    punct_model = None

            logger.info("Running VAD...")
            
            # [兼容性修复] PyTorch 2.6+ 默认 weights_only=True 会破坏 pyannote/whisperx 加载
            # 临时修改 torch.load 以强制 weights_only=False
            _original_load = torch.load
            def _robust_load(*args, **kwargs):
                kwargs['weights_only'] = False
                return _original_load(*args, **kwargs)
            torch.load = _robust_load
            
            try:
                vad_model = load_vad_model(torch.device("cpu"), use_auth_token=None)
            finally:
                # 恢复原始函数，虽然在这个线程影响不大
                torch.load = _original_load
            
            logger.info("Running VAD...")
            # Returns SlidingWindowFeature (scores)
            vad_outputs = vad_model({"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000})
            
            # Helper to Binarize scores into segments
            try:
                from pyannote.audio.utils.signal import Binarize
                binarize_fn = Binarize(offset=0.5, onset=0.5, min_duration_off=0.1, min_duration_on=0.1)
                vad_segments = binarize_fn(vad_outputs)
            except ImportError:
                logger.warning("Could not import Binarize, attempting alternative path.")
                # 尝试从 pyannote 其他模块路径导入 Binarize
                # 手动处理滑动窗口特征较为复杂，优先复用现有工具
                try: 
                    from pyannote.audio.pipelines.utils import Binarize
                    binarize_fn = Binarize(offset=0.5, onset=0.5, min_duration_off=0.1, min_duration_on=0.1)
                    vad_segments = binarize_fn(vad_outputs)
                except:
                     # 如果导入彻底失败：将整个音频视为一个片段
                     logger.error("Binarization failed. Using full audio.")
                     from pyannote.core import Segment, Annotation
                     vad_segments = Annotation()
                     vad_segments[Segment(0, len(audio)/16000)] = "speech"

            logger.info(f"VAD finished. Result type: {type(vad_segments)}")

            # Local merge_chunks implementation to avoid import issues
            def local_merge_chunks(segments, chunk_size, onset=0.5, offset=0.5):
                """
                Input: segments (pyannote Annotation, pandas DataFrame, or list of dicts/objects)
                """
                logger.info(f"local_merge_chunks input type: {type(segments)}")

                # Handle pandas DataFrame
                if hasattr(segments, "to_dict") and hasattr(segments, "columns"):
                    segments = segments.to_dict('records')
                # Handle pyannote Annotation object
                elif hasattr(segments, "itertracks"):
                    simple_segs = []
                    for segment, _, _ in segments.itertracks(yield_label=True):
                        simple_segs.append({"start": segment.start, "end": segment.end})
                    segments = simple_segs
                
                if not segments: return []

                # Helper to get start/end regardless of dict or object
                def get_time(seg):
                    if isinstance(seg, dict):
                        return seg.get('start'), seg.get('end')
                    elif hasattr(seg, 'start') and hasattr(seg, 'end'):
                        return seg.start, seg.end
                    # Fallback for tuple/list? (start, end)
                    if isinstance(seg, (list, tuple)) and len(seg) >= 2:
                        return seg[0], seg[1]
                    return None, None

                curr_start, _ = get_time(segments[0])
                if curr_start is None:
                    # 转换失败或格式未知
                    logger.error(f"Unknown segment format: {segments[0]}")
                    return []

                merged = []
                curr_end = 0
                
                for seg in segments:
                    seg_start, seg_end = get_time(seg)
                    if seg_start is None: continue

                    if (seg_end - curr_start > chunk_size) and (curr_end - curr_start > 0):
                        merged.append({"start": curr_start, "end": curr_end})
                        curr_start = seg_start
                    
                    curr_end = seg_end
                
                merged.append({"start": curr_start, "end": curr_end})
                return merged

            logger.info(f"VAD found segments. Merging...")
            # chunk_size=30s is safe for 1GB memory? 
            merged_segments = local_merge_chunks(vad_segments, chunk_size=30)
            
            logger.info(f"Processing {len(merged_segments)} chunks with Sherpa (VAD-based)...")
            logger.info(f"Processing {len(merged_segments)} chunks with Sherpa (VAD-based)...")
            
            # [稳定性修复] 强制限制最大切片时长
            # 如果 VAD 返回超长片段 (例如 VAD 失败导致全音频返回)，必须强制切分
            # 否则 Sherpa Parakeet 模型在 CPU 下会因 Tensor 形状过大导致崩溃 (Shape mismatch)。
            final_segments = []
            MAX_CHUNK = 30.0 # seconds
            
            for seg in merged_segments:
                start = seg['start']
                end = seg['end']
                duration = end - start
                
                if duration <= MAX_CHUNK:
                    final_segments.append(seg)
                else:
                    # Split huge segment
                    curr = start
                    while curr < end:
                        next_end = min(curr + MAX_CHUNK, end)
                        final_segments.append({"start": curr, "end": next_end})
                        curr = next_end
            
            merged_segments = final_segments
            total_chunks = len(merged_segments)
            logger.info(f"Refined into {total_chunks} chunks (Max {MAX_CHUNK}s).")
            
            
            final_results = []
            
            start_process_time = time.time()
            
            for i, seg in enumerate(merged_segments):
                if self._is_cancelled: return

                seg_start = seg['start']
                seg_end = seg['end']
                
                # Progress report
                percent = int(20 + (i / total_chunks) * 80)
                self.progress.emit(f"正在转写片段 {i+1}/{total_chunks} ({seg_start:.1f}s - {seg_end:.1f}s)...")
                self.progress_percent.emit(percent)
                
                # Extract chunk
                s_sample = int(seg_start * 16000)
                e_sample = int(seg_end * 16000)
                chunk_audio = audio[s_sample:e_sample]
                
                # Decode chunk
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, chunk_audio)
                recognizer.decode_stream(stream)
                
                chunk_res = stream.result
                text = chunk_res.text.strip()
                
                if text:
                    # Apply Punctuation if model loaded
                    if punct_model:
                        try:
                            # Re-punctuate the segment text
                            text = punct_model.add_punctuation(text)
                            logger.debug(f"Punctuated: {text}")
                        except Exception as e:
                            logger.warning(f"Punctuation failed: {e}")

                    # Sherpa 时间戳相对于切片开始
                    # tokens 通常是中文汉字或子词
                    # 简单处理：添加片段条目
                    final_results.append({
                        "start": seg_start, # 近似开始时间 (VAD Start)
                        "end": seg_end,     # 近似结束时间 (VAD End)
                        "text": text
                    })
                    logger.debug(f"片段 {i}: {text}")

            end_process_time = time.time()
            logger.info(f"Sherpa transcription finished in {end_process_time - start_process_time:.2f}s")
            
            # 3.5 Post-processing: Post Segmentation (Auto Sentence Split)
            if punct_model and final_results:
                logger.info("Running automatic sentence segmentation...")
                try:
                    final_results = self._post_process_segmentation(final_results)
                    logger.info(f"Segmentation finished. New segments count: {len(final_results)}")
                except Exception as e:
                    logger.error(f"Segmentation failed: {e}. Returning original valid results.")

            # Alignment (WhisperX Force Alignment)
            if self.align and final_results:
                try:
                    self.progress.emit("正在进行音频对齐 (Aligning)...")
                    
                    # 1. Detect language if needed
                    align_lang = self.language
                    if not align_lang:
                        # 组合文本进行检测
                        full_text = " ".join([s['text'] for s in final_results])
                        try:
                            align_lang = langdetect.detect(full_text)
                            logger.info(f"Detected language for alignment: {align_lang}")
                        except Exception as ld_e:
                            logger.warning(f"Language detection failed: {ld_e}. Defaulting to 'en'.")
                            align_lang = "en"
                    
                    # 2. Load Alignment Model
                    align_model_dir = os.path.join(self.models_root, "alignment")
                    os.makedirs(align_model_dir, exist_ok=True)
                    
                    # Determine device for alignment (can use same as sherpa provided it's supported)
                    # WhisperX align supports cpu and cuda
                    align_device = "cuda" if "cuda" in self.device and torch.cuda.is_available() else "cpu"

                    model_a, metadata = whisperx.load_align_model(
                        language_code=align_lang,
                        device=align_device,
                        model_dir=align_model_dir
                    )
                    
                    # 3. 准备 whisperx 片段 (已包含 text, start, end)
                    
                    # 4. 运行强制对齐
                    result_aligned = whisperx.align(
                        final_results,
                        model_a,
                        metadata,
                        audio,
                        align_device,
                        return_char_alignments=True
                    )
                    
                    # 5. 清理资源
                    del model_a
                    if align_device == "cuda": torch.cuda.empty_cache()
                    gc.collect()
                    
                    # 6. 更新结果并标准化 (适配 SRTProcessor)
                    if "segments" in result_aligned:
                        aligned_segments = []
                        for seg in result_aligned["segments"]:
                            item = {
                                "start": seg.get("start", 0),
                                "end": seg.get("end", 0),
                                "text": seg.get("text", "")
                            }
                            # 关键：保留 words/chars 用于 SRTProcessor
                            if "words" in seg: item["words"] = seg["words"]
                            if "chars" in seg: item["chars"] = seg["chars"]
                            aligned_segments.append(item)
                        final_results = aligned_segments
                        logger.info(f"Alignment finished. {len(final_results)} segments aligned.")

                except Exception as ae:
                    logger.error(f"Alignment failed: {ae}")
                    self.progress.emit(f"对齐失败 (跳过): {ae}")

            # 4. Final SRT Post-Processing (Leveraging Char-level Timestamps if available)
            if final_results:
                try:
                    from .srt_processor import SRTProcessor
                    logger.info("Running final SRT post-processing...")
                    
                    # Need to determine lang if not set
                    proc_lang = align_lang if (self.align and align_lang) else (self.language or "zh")
                    
                    final_results = SRTProcessor.process_segments(
                        final_results, 
                        lang=proc_lang
                    )
                except Exception as pe:
                    logger.warning(f"Final post-processing warning: {pe}")

            # 5. Return results (List of dicts)
            self.finished.emit(True, final_results)
            self.progress.emit("转写完成 (Sherpa)")
            self.progress_percent.emit(100)
            
        except Exception as e:
            logger.error(f"Sherpa transcription failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.finished.emit(False, str(e))


    def _post_process_segmentation(self, results):
        """
        移植自 SRTToolbox.regroup_by_punctuation
        基于标点符号重新切分文本，同时通过字符级插值保留时间轴。
        包含长句逗号切分逻辑。
        """
        if not results: return []

        # 1. Extract all chars with estimated timing
        char_times = [] # [(start_ms, end_ms), char]
        
        for seg in results:
            text = seg['text'].strip()
            if not text: continue
            
            start_ms = seg['start'] * 1000
            end_ms = seg['end'] * 1000
            duration = end_ms - start_ms
            char_count = len(text)
            
            if char_count == 0: continue
            
            for i, char in enumerate(text):
                # Linear interpolation
                c_start = start_ms + (i / char_count) * duration
                c_end = start_ms + ((i + 1) / char_count) * duration
                char_times.append((c_start, c_end, char))
        
        if not char_times: return results

        full_text = "".join([c[2] for c in char_times])
        
        # 2. Split by punctuation (keeping delimiters)
        # Matches: 。！？.!? 
        sentences = re.split(r'([。！？.!?])', full_text)
        
        # 3. Combine sentences with their punctuation
        initial_sentences = []
        for i in range(0, len(sentences)-1, 2):
            initial_sentences.append(sentences[i] + sentences[i+1])
        if len(sentences) % 2 != 0 and sentences[-1]:
            initial_sentences.append(sentences[-1])
            
        # 4. Process long sentences (Split by comma)
        MAX_CHARS = 30 # Threshold for splitting
        final_sentences = []
        
        for sent in initial_sentences:
            sent = sent.strip()
            if not sent: continue
            
            if len(sent) > MAX_CHARS:
                # Try to split by comma if too long
                # Find commas
                commas = [m.start() for m in re.finditer(r'[，,]', sent)]
                if commas:
                    # Find comma closest to middle
                    mid = len(sent) // 2
                    best_comma = min(commas, key=lambda x: abs(x - mid))
                    
                    # Split (include comma in first part)
                    p1 = sent[:best_comma+1]
                    p2 = sent[best_comma+1:]
                    
                    if p1.strip(): final_sentences.append(p1)
                    if p2.strip(): final_sentences.append(p2)
                    continue
            
            final_sentences.append(sent)

        # 5. Map back to time
        new_results = []
        current_char_idx = 0
        
        for sent in final_sentences:
            sent = sent.strip()
            if not sent: continue
            
            sent_len = len(sent)
            # Find in full_text to safeguard index
            start_idx = full_text.find(sent, current_char_idx)
            if start_idx == -1: 
                # Should not happen typically
                current_char_idx += sent_len 
                continue 
                
            end_idx = start_idx + sent_len
            
            # Map back to time
            # char_times index corresponds to full_text index
            if start_idx < len(char_times) and (end_idx-1) < len(char_times):
                s_time = char_times[start_idx][0]
                e_time = char_times[end_idx-1][1]
                
                new_results.append({
                    "start": s_time / 1000.0,
                    "end": e_time / 1000.0,
                    "text": sent
                })
            
            current_char_idx = end_idx
            
        return new_results


class SherpaEngine(QObject):
    task_started = pyqtSignal()
    task_progress = pyqtSignal(str, int) 
    task_finished = pyqtSignal(bool, object) 
    
    def __init__(self, model_manager):
        super().__init__()
        self.manager = model_manager
        self.worker = None
        
    def is_running(self):
        return self.worker is not None and self.worker.isRunning()
        
    def start_transcription(self, audio_path, device="cuda", align=True, language=None, initial_prompt=None, vad_filter=True):
        if self.is_running(): return False, "Task already running"
        
        # 1. 获取模型路径
        # 优先使用 Manager 的路径，但需检查是否为 Sherpa 模型
        model_path = self.manager.get_model_path()
        
        # 默认 Sherpa 模型 ID
        DEFAULT_SHERPA_ID = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
        
        # 检查是否为有效 Sherpa 路径 (含 tokens.txt)
        is_valid_sherpa = False
        if model_path and os.path.exists(model_path):
            if "tokens.txt" in os.listdir(model_path):
                is_valid_sherpa = True
        
        if not is_valid_sherpa:
            # 尝试获取默认 Sherpa 模型路径
            model_path = self.manager.get_model_path(DEFAULT_SHERPA_ID)
            
            # 如果还不存在，尝试下载
            if not model_path:
                if self.manager.download_model(DEFAULT_SHERPA_ID):
                    self.task_progress.emit(f"Sherpa 模型未找到，已开始自动下载: {DEFAULT_SHERPA_ID}", 0)
                    return True, "Starts downloading..." # Special return? Or block? 
                    # WhisperEngine 也是异步加载，这里稍微不同，WhisperEngine 假设已存在或 Worker 内部加载。
                    # 为了简化，如果需要下载，我们可以让 Manager 下载，或者在 Worker 中尝试下载。
                    # 由于 Manager.download_model 是异步的，这里直接返回可能导致 Worker 立即启动失败。
                    # 我们这里简单处理：如果未就绪，返回失败提示下载。
                    return False, f"默认 Sherpa 模型 ({DEFAULT_SHERPA_ID}) 未下载，请先在设置中下载。"
        
        # 尝试解析标点模型路径 (可选)
        PUNCT_ID = "csukuangfj/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12"
        punct_path = self.manager.get_model_path(PUNCT_ID)
        if not punct_path:
             logger.info("Punctuation model not found locally. Skipping punctuation.")
        
        self.worker = SherpaTranscriptionWorker(
            model_path,
            audio_path,
            models_root=self.manager.models_root,
            device=device,
            language=language,
            punct_model_path=punct_path,
            align=align
        )
        
        self.worker.progress.connect(lambda msg: self.task_progress.emit(msg, 0))
        self.worker.progress_percent.connect(lambda p: self.task_progress.emit("", p))
        self.worker.finished.connect(self._on_worker_finished)
        
        self.task_started.emit()
        self.worker.start()
        
        return True, "Started"

    def cancel(self):
        if self.worker:
            self.worker.cancel()
    def _on_worker_finished(self, success, result):
        self.task_finished.emit(success, result)
        self.worker = None
