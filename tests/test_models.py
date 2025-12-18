import pytest
import os
import tempfile
import json

def test_project_model_initial_state(project_model):
    assert project_model.subtitle_data == []
    assert project_model.source_file is None
    assert project_model.target_file is None

def test_project_model_insert_delete(project_model):
    # 模拟添加一行
    project_model.subtitle_data = [{'source': 'test'}]
    assert len(project_model.subtitle_data) == 1
    
    # 插入行 (逻辑在 insert_row)
    project_model.insert_row(1)
    assert len(project_model.subtitle_data) == 2
    
    # 删除行
    project_model.delete_row(0)
    assert len(project_model.subtitle_data) == 1

def test_project_model_persistence(project_model, sample_subtitle_data):
    project_model.subtitle_data = sample_subtitle_data
    
    with tempfile.NamedTemporaryFile(suffix='.kcp', delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        # 保存项目
        success = project_model.save_project(tmp_path)
        assert success is True
        
        # 加载项目
        new_model = project_model.__class__()
        success = new_model.load_project(tmp_path)
        assert success is True
        assert len(new_model.subtitle_data) == len(sample_subtitle_data)
        assert new_model.subtitle_data[0]['source']['text'] == 'Hello World'
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
