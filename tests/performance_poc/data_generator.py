import numpy as np
import logging

def generate_fake_waveform(duration_sec=3600, chunk_ms=10):
    """
    生成模拟的音频峰值数据 (Min/Max)
    默认生成 1小时数据 (3600s), 每 10ms 一个点 -> 360,000 个点
    """
    total_chunks = int(duration_sec * 1000 / chunk_ms)
    print(f"Generating {total_chunks} data points for {duration_sec}s audio...")
    
    # 随机生成 -1.0 到 1.0 的模拟波形
    # 使用随机步游走模拟自然波形
    # 先生成单通道
    np.random.seed(42)
    noise = np.random.normal(0, 0.3, total_chunks)
    
    # 模拟一些起伏 (envelope)
    t = np.linspace(0, duration_sec, total_chunks)
    envelope = np.sin(t * 0.1) * 0.5 + 0.5 # 0-1 缓慢变化
    
    data = noise * envelope
    
    # 构造 (min, max)
    # 实际上真实的 peaks 是一个块内的极值。这里我们简单模拟：
    # Max 是 abs(data), Min 是 -abs(data) 加上一点随机抖动
    maxs = np.abs(data)
    mins = -maxs
    
    # 归一化到 -1 ~ 1
    maxs = np.clip(maxs, 0, 1)
    mins = np.clip(mins, -1, 0)
    
    # Stack: (N, 2)
    peaks = np.column_stack((mins, maxs)).astype(np.float32)
    print(f"Data generated. Shape: {peaks.shape}, Size: {peaks.nbytes / 1024 / 1024:.2f} MB")
    return peaks

if __name__ == "__main__":
    generate_fake_waveform()
