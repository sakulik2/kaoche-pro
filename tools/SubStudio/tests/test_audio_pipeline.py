import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import time
from PyQt6.QtCore import QObject, pyqtSignal

# Mock AudioProcessor to avoid QThread loop complexity without QApplication
# but we want to test the run logic.
from tools.SubStudio.core.audio_processor import AudioProcessor

class TestAudioPipeline(unittest.TestCase):
    
    def test_downsample_algorithm(self):
        """测试核心降采样与峰值计算逻辑"""
        # 手动模拟 run 中的 numpy 处理逻辑
        
        # 1. 构造假 PCM 数据 (16kHz, 1s) -> 16000 samples
        # 频率 100Hz Sine Wave
        sample_rate = 8000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        # 振幅 32000 (接近 int16 max)
        sine_wave = (32000 * np.sin(2 * np.pi * 100 * t)).astype(np.int16)
        
        # 2. 模拟参数
        chunk_ms = 10
        samples_per_chunk = int(sample_rate * (chunk_ms / 1000)) # 80 samples
        
        # 3. 运行算法
        length = len(sine_wave)
        pad_size = samples_per_chunk - (length % samples_per_chunk)
        if pad_size != samples_per_chunk:
            sine_wave = np.pad(sine_wave, (0, pad_size), mode='constant')
            
        reshaped = sine_wave.reshape(-1, samples_per_chunk)
        mins = reshaped.min(axis=1)
        maxs = reshaped.max(axis=1)
        peaks = np.column_stack((mins, maxs)).astype(np.float32) / 32768.0
        
        # 4. 验证
        expected_chunks = int(duration * 1000 / chunk_ms)
        self.assertEqual(len(peaks), expected_chunks, "生成的 Chunk 数量应符合 Duration/ChunkMS")
        
        # 峰值应该接近 1.0
        max_val = peaks.max()
        self.assertAlmostEqual(max_val, 32000/32768, delta=0.1, msg="正弦波峰值应被正确提取")
        
    @patch('subprocess.Popen')
    def test_ffmpeg_pipeline_invocation(self, mock_popen):
        """验证是否正确调用了 FFmpeg 管道命令"""
        processor = AudioProcessor("test_video.mp4")
        
        # Mock process
        mock_process = MagicMock()
        mock_process.stdout.read.side_effect = [b'', b''] # Empty read immediately
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process
        
        processor.run()
        
        # 检查命令参数
        args, _ = mock_popen.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-ac", cmd)
        self.assertIn("1", cmd) # Mono
        self.assertIn("-f", cmd)
        self.assertIn("s16le", cmd) # PCM
        self.assertEqual(cmd[-1], "-") # Pipe

if __name__ == "__main__":
    unittest.main()
