
import sys
import os

# 确保项目根目录在 path 中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.api.api_client import APIClient
from core.models.subtitle import SubtitleItem, SubtitlePair
from core.parsers.subtitle_parser import parse_subtitle_file

def test_api_client_import():
    print("Testing APIClient import from core.api...")
    # 模拟配置
    config = {'id': 'test', 'api_type': 'openai'}
    client = APIClient(config, 'key', 'model')
    assert client.api_type == 'openai'
    print("✓ APIClient import successful")

def test_model_compatibility():
    print("Testing SubtitleItem model and dict compatibility...")
    item = SubtitleItem(text="Hello", start=1.0, end=2.0)
    
    # 属性访问
    assert item.text == "Hello"
    # 字典式访问 (兼容性检查)
    assert item['text'] == "Hello"
    assert item['start'] == 1.0
    
    # 转字典
    d = item.to_dict()
    assert d['text'] == "Hello"
    print("✓ SubtitleItem compatibility successful")

def test_parser_output():
    print("Testing subtitle_parser output type...")
    # 创建一个临时测试文件
    test_file = "test_sub.srt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("1\n00:00:01,000 --> 00:00:02,000\nTest content\n")
    
    try:
        results = parse_subtitle_file(test_file)
        assert len(results) > 0
        assert isinstance(results[0], SubtitleItem)
        assert results[0].text == "Test content"
        print("✓ Parser returned SubtitleItem instances")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

if __name__ == "__main__":
    try:
        test_api_client_import()
        test_model_compatibility()
        test_parser_output()
        print("\n✨ All refactoring integrity tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
