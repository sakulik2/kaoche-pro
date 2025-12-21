import os
import torch

# 极致 Monkeypatch：确保任何地方调用的 torch.load 都使用 weights_only=False
_original_torch_load = torch.load
def _robust_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _robust_torch_load

import whisperx
import time

def run_poc():
    sample_video = r"e:\code\kaoche-pro\sample\The Horrors of Waking Up DURING Surgery [sQaxxOo72-I].mkv"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    batch_size = 16 
    compute_type = "float16" 

    print(f"--- SubStudio AI POC (PyTorch 2.8 Ultimate Patch) ---")
    print(f"Device: {device}")
    print(f"Sample: {os.path.basename(sample_video)}")
    
    start_all = time.time()

    # 1. Load Audio
    print("\n[1/3] Loading audio...")
    audio = whisperx.load_audio(sample_video)
    
    # 2. Transcribe with Faster-Whisper
    print("[2/3] Transcribing (Faster-Whisper)...")
    # 第一次运行会下载模型，可能较慢
    model = whisperx.load_model("small", device, compute_type=compute_type)
    result = model.transcribe(audio, batch_size=batch_size, language="en") # 显式指定语言减少检测开销
    print(f"Transcription complete. Segments found: {len(result['segments'])}")

    # 3. Align with Wav2Vec2
    print("[3/3] Aligning (Wav2Vec2)...")
    # 这一步也会下载对齐模型
    model_a, metadata = whisperx.load_align_model(language_code="en", device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    print("Alignment complete.")

    end_all = time.time()
    
    # Summary
    print("\n--- Final Report ---")
    print(f"Total Time: {end_all - start_all:.2f}s")
    if torch.cuda.is_available():
        vram = torch.cuda.max_memory_allocated() / 1024**3
        total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"Max VRAM Usage: {vram:.2f} / {total_vram:.2f} GB")
    
    print("\n[INFO] AI 字幕生成成功。")

if __name__ == "__main__":
    try:
        run_poc()
    except Exception as e:
        import traceback
        print(f"\n[ERROR] POC Failed: {str(e)}")
        traceback.print_exc()
