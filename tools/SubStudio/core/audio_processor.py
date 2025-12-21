import subprocess
import os
import numpy as np
import hashlib
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class AudioProcessor(QThread):
    """
    后台音频处理引擎
    利用 FFmpeg 管道读取音频流，并计算用于绘制波形的峰值数据 (Min/Max)
    """
    progress_changed = pyqtSignal(int)
    finished = pyqtSignal(bool, object) # success, data (list of tuples or error str)

    def __init__(self, video_path, sample_rate=8000, ms_per_pixel=100):
        super().__init__()
        self.video_path = video_path
        self.sample_rate = sample_rate
        # 实际上我们不是 per pixel，而是 per chunk。
        # 假设前端缩放 PPS=0.1 (1px=10ms)，那么 100ms 就是 10px 宽的一个数据点。
        # 为了足够精细支持放大，我们目标是每 10ms 一个点 (100Hz 刷新率)
        self.chunk_size_ms = 10 
        self.is_cancelled = False

    def _get_cache_path(self, video_path):
        """生成全局唯一的缓存文件路径，避免在源文件夹下产生 .npy 文件"""
        # 使用项目根目录下的 cache/waveforms 目录
        cache_dir = os.path.join(os.getcwd(), 'cache', 'waveforms')
        try:
            os.makedirs(cache_dir, exist_ok=True)
            # 使用路径的 MD5 作为文件名
            path_hash = hashlib.md5(video_path.encode('utf-8')).hexdigest()
            return os.path.join(cache_dir, f"{path_hash}.npy")
        except Exception as e:
            logger.warning(f"Failed to create cache dir: {e}. Falling back to source folder.")
            return f"{video_path}.waveform.npy"

    def run(self):
        try:
            cache_path = self._get_cache_path(self.video_path)
            
            # 1. 尝试读取缓存
            if os.path.exists(cache_path):
                logger.info(f"Loading waveform from cache: {cache_path}")
                try:
                    peaks = np.load(cache_path)
                    # 简单校验
                    if peaks.ndim == 2 and peaks.shape[1] == 2:
                        self.finished.emit(True, peaks)
                        return
                    else:
                        logger.warning("Invalid cache format, regenerating...")
                except Exception as e:
                    logger.warning(f"Failed to load cache: {e}")

            # 2. FFmpeg 提取
            cmd = [
                "ffmpeg",
                "-i", self.video_path,
                "-vn",              # No video
                "-ac", "1",         # Mono
                "-ar", str(self.sample_rate), # 8kHz
                "-f", "s16le",      # 16-bit PCM
                "-"                 # stdout
            ]
            
            logger.info(f"Starting generic audio extraction: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL,
                bufsize=10**7 
            )
            
            # 使用 List 缓冲读取，避免大量 bytes copy
            chunks = []
            chunk_read_size = 4096 * 1024 
            
            while True:
                if self.is_cancelled:
                    process.terminate()
                    return
                
                chunk = process.stdout.read(chunk_read_size)
                if not chunk:
                    break
                chunks.append(chunk)
                
                if len(chunks) % 10 == 0:
                     self.progress_changed.emit(-1)
            
            process.wait()
            
            if self.is_cancelled: return
            
            if not chunks:
                self.finished.emit(False, "No audio data extracted")
                return

            # Combine chunks
            raw_data = b"".join(chunks)
            chunks = None # Release memory

            # NumPy 处理
            # int16 范围 -32768 to 32767
            audio_array = np.frombuffer(raw_data, dtype=np.int16)
            
            if len(audio_array) == 0:
                self.finished.emit(False, "Empty audio stream")
                return
 
            # 计算峰值
            # 目标：每 self.chunk_size_ms 毫秒提取一个 (min, max)
            samples_per_chunk = int(self.sample_rate * (self.chunk_size_ms / 1000))
            if samples_per_chunk < 1: samples_per_chunk = 1
            
            # 补齐数组长度以便 reshape
            length = len(audio_array)
            pad_size = samples_per_chunk - (length % samples_per_chunk)
            if pad_size != samples_per_chunk:
                audio_array = np.pad(audio_array, (0, pad_size), mode='constant')
            
            # Reshape: (chunks, samples_per_chunk)
            # 使用 reshape(-1, N) 极其高效，无内存拷贝
            reshaped = audio_array.reshape(-1, samples_per_chunk)
            
            # 关键优化：NumPy 向量化计算 Min/Max
            mins = reshaped.min(axis=1)
            maxs = reshaped.max(axis=1)
            
            # 归一化并合并为 (N, 2)
            # float32 足够精度且节省内存
            peaks = np.column_stack((mins, maxs)).astype(np.float32) / 32768.0
            
            # 3. 写入缓存
            try:
                np.save(cache_path, peaks)
                logger.info(f"Waveform cached to {cache_path}")
            except Exception as e:
                logger.warning(f"Failed to save cache: {e}")
            
            logger.info(f"Audio extraction done. Generated {len(peaks)} peak points.")
            self.finished.emit(True, peaks)
            
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            self.finished.emit(False, str(e))
    
    def cancel(self):
        self.is_cancelled = True
