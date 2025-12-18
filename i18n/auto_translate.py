"""
自动翻译脚本
使用项目的 LLM 基础设施自动翻译 .ts 文件中的未完成条目
"""

import sys
import os
import xml.etree.ElementTree as ET
import json
import logging
import asyncio

# 添加项目根目录到 path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api_client import APIClient, load_providers_config
from core.llm_utils import parse_json_from_response

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kaoche_en.ts')

def load_settings():
    """加载设置"""
    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'settings.json')
    if os.path.exists(settings_path):
        with open(settings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_api_client():
    """初始化 API 客户端"""
    settings = load_settings()
    providers = load_providers_config()
    
    # 获取配置
    api_config = settings.get('api', {})
    provider_id = api_config.get('provider', 'openai')
    
    # 优先使用 api.api_key，如果没有则尝试从 providers 里找
    api_key = api_config.get('api_key')
    
    # 如果 api.api_key 为空，尝试查找具体的 provider key
    if not api_key:
         # 尝试 api.api_keys.xxxx
         api_key = api_config.get('api_keys', {}).get(provider_id)
         
    if not api_key:
        # 尝试 providers.xxxx.api_key
        provider_cfg = providers.get(provider_id, {})
        api_key = provider_cfg.get('api_key')
        
    if not api_key:
        logger.error(f"未找到 API Key (Provider: {provider_id})")
        sys.exit(1)
        
    # 获取模型
    model = api_config.get('model')
    if not model:
        model = providers.get(provider_id, {}).get('default_model', 'gpt-4')
        
    provider_config = providers.get(provider_id, {'id': provider_id, 'api_type': 'openai'}) # 默认 fallback
    
    logger.info(f"使用 API: {provider_id} ({model})")
    return APIClient(provider_config, api_key, model)

def translate_batch(client, texts):
    """批量翻译"""
    system_prompt = """You are a professional software localization expert. 
Your task is to translate the following UI strings from Chinese (Simplified) to English.
Ensure the translations are concise, professional, and suitable for a software interface.
Maintain any placeholders like {} or {0} exactly as they are.
Output ONLY a JSON array of strings corresponding to the input order.
Example Input: ["文件", "打开"]
Example Output: ["File", "Open"]"""

    user_prompt = json.dumps(texts, ensure_ascii=False)
    
    try:
        response = client.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True
        )
        
        translations = parse_json_from_response(response['text'])
        
        if not isinstance(translations, list) or len(translations) != len(texts):
            logger.error(f"翻译结果数量不匹配或格式错误: 期望 {len(texts)}，实际 {len(translations) if isinstance(translations, list) else 'Not List'}")
            return []
            
        return translations
        
    except Exception as e:
        logger.error(f"翻译请求失败: {e}")
        return []

def main():
    if not os.path.exists(TS_FILE):
        logger.error(f"找不到 TS 文件: {TS_FILE}")
        return

    logger.info(f"正在解析: {TS_FILE}")
    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    
    # 查找所有未完成的翻译
    unfinished_nodes = []
    
    # context/message/translation[@type='unfinished']
    for context in root.findall('context'):
        for message in context.findall('message'):
            translation = message.find('translation')
            if translation is not None and translation.get('type') == 'unfinished':
                source = message.find('source')
                if source is not None and source.text:
                    # 排除已经是英文的 (简单启发式: 看是否包含中文)
                    # 但考虑到 kaoche-pro 是中文应用，source 大多是中文
                    # TODO: 如果 source 是空的或者纯符号，可能不需要翻译
                    unfinished_nodes.append((translation, source.text))
    
    total = len(unfinished_nodes)
    logger.info(f"发现 {total} 个未翻译条目")
    
    if total == 0:
        logger.info("没有什么需要翻译的。")
        return

    client = get_api_client()
    
    batch_size = 20
    processed = 0
    
    # 限制用于测试
    limit_count = 0 
    if limit_count:
         unfinished_nodes = unfinished_nodes[:limit_count]
         total = len(unfinished_nodes)
         logger.info(f"测试模式: 仅翻译前 {total} 条")

    # 分批处理
    for i in range(0, total, batch_size):
        batch = unfinished_nodes[i : i + batch_size]
        texts = [item[1] for item in batch]
        
        logger.info(f"正在翻译批次 {i//batch_size + 1}/{(total + batch_size - 1)//batch_size} ({len(texts)} 条)...")
        
        translated_texts = translate_batch(client, texts)
        
        if not translated_texts:
            logger.warning("批次翻译失败，跳过")
            continue
            
        # 更新 XML
        for j, translation_text in enumerate(translated_texts):
             if j < len(batch):
                 node = batch[j][0]
                 node.text = translation_text
                 # 移除 type="unfinished"
                 if 'type' in node.attrib:
                     del node.attrib['type']
        
        processed += len(translated_texts)
        # 简单保存一下进度 (可选)
        
    # 保存文件
    # write manually to control format
    with open(TS_FILE, 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(b'<!DOCTYPE TS>\n')
        tree.write(f, encoding='utf-8', xml_declaration=False)
        
    logger.info(f"翻译完成! 共更新 {processed} 条。已保存到 {TS_FILE}")
    logger.info("请运行 'python compile_ts.py' 重新生成 .qm 文件")

if __name__ == '__main__':
    main()
