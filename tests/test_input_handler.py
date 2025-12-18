import pytest
import os
from core.services.input_handler import InputOrchestrator, SuggestedAction, InputType

@pytest.fixture
def orchestrator():
    return InputOrchestrator()

def test_video_detection(orchestrator):
    # 纯净状态
    res = orchestrator.decide_action("movie.mp4", has_video=False, has_subtitle_data=False)
    assert res['action'] == SuggestedAction.LOAD_VIDEO
    
    # 冲突状态
    res = orchestrator.decide_action("movie.mkv", has_video=True, has_subtitle_data=False)
    assert res['action'] == SuggestedAction.VIDEO_CONFLICT

def test_monolingual_logic(orchestrator):
    # 空白状态拖入单语 (假设是英文)
    # 注意：这里我们没法在测试里真的读文件，所以我们主要测试 decide_action 的逻辑分支
    # InputOrchestrator._detect_content_language 会被调用，但我们可以通过 mock 或直接测决策逻辑
    
    # 1. 只有原文时拖入单语
    res = orchestrator.decide_action("sub.srt", has_video=False, has_subtitle_data=False, has_source_file=True, has_target_file=False)
    assert res['action'] == SuggestedAction.SUGGEST_TARGET
    
    # 2. 已有双语数据（has_subtitle_data=True）时拖入单语
    res = orchestrator.decide_action("extra.txt", has_video=False, has_subtitle_data=True, has_source_file=False, has_target_file=False)
    assert res['action'] == SuggestedAction.FULL_CONFLICT

def test_bilingual_detection_logic(orchestrator, tmp_path):
    # 创建一个模拟的双语文件内容
    # 增加内容长度以避开 "total_chars < 5" 的过滤
    bi_file = tmp_path / "bilingual.txt"
    content = [
        "This is a long English sentence for testing.",
        "这是一句足够长的中文句子，用于双语测试。",
        "And another English line that is quite long.",
        "以及另一句同样长且包含汉字的中文行。"
    ]
    bi_file.write_text("\n".join(content), encoding="utf-8")
    
    # 1. 纯净加载
    res = orchestrator.decide_action(str(bi_file), has_video=False, has_subtitle_data=False)
    assert res['type'] == InputType.BILINGUAL
    assert res['action'] == SuggestedAction.LOAD_BILINGUAL
    
    # 2. 冲突加载
    res = orchestrator.decide_action(str(bi_file), has_video=False, has_subtitle_data=True)
    assert res['action'] == SuggestedAction.BILINGUAL_CONFLICT
