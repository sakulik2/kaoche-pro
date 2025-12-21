import os
# 设置镜像源
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from huggingface_hub import hf_hub_download
import shutil

def main():
    repo_id = "deepdml/faster-whisper-large-v3-turbo-ct2"
    base_dir = r"e:\code\kaoche-pro\tools\SubStudio"
    local_dir = os.path.join(base_dir, "models", "whisper", "large-v3-turbo")
    
    os.makedirs(local_dir, exist_ok=True)

    # 用户提示 vocabulary.txt 实际为 json，很可能 repo 里是 vocabulary.json
    # 我们尝试下载 vocabulary.json，如果需要，再改名为 vocabulary.txt (Faster-Whisper 默认找 .txt)
    files = ["vocabulary.json"] 

    print("=== SubStudio Vocabulary Fixer ===")
    print(f"Repo    : {repo_id}")
    print(f"Path    : {local_dir}")

    for file in files:
        print(f"\nFetching {file}...")
        try:
            path = hf_hub_download(
                repo_id=repo_id,
                filename=file,
                local_dir=local_dir,
                local_dir_use_symlinks=False,
                resume_download=True
            )
            print(f"Success: {path}")
            
            # 检查 content，如果是 JSON 且 Faster-Whisper 需要 .txt，我们可能需要处理
            # 但通常 CT2 模型只需要 tokenizer.json 即可，或者 vocab.txt (Flat format)
            # 如果下载下来的是 json，我们将其保留，faster-whisper 1.x 加载 tokenizer.json 优先
            
        except Exception as e:
            print(f"Error downloading {file}: {e}")
            # 如果 json 不存在，可能还是 txt 但内容是 json? 
            # 或者是 user 意思是把 tokenizer.json 当作 vocab 用？
            # 暂时不做过多假设，先试 json

if __name__ == "__main__":
    main()
