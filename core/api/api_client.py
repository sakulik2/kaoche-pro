"""
统一的 API 客户端
支持多个 AI 提供商：OpenAI, Anthropic, Google Gemini
"""

import json
import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class APIClient:
    """
    统一的 LLM API 客户端，处理不同供应商的请求分发、密钥管理及重试逻辑。
    """
    
    def __init__(self, provider_config: Dict[str, Any], api_key: str, model: str):
        """
        初始化 API 客户端
        
        Args:
            provider_config: 提供商配置字典，包含 id, api_type, api_base 等
            api_key: API 密钥
            model: 模型名称
        """
        # 提取配置
        self.provider_id = provider_config['id']
        self.api_type = provider_config.get('api_type', 'openai')
        self.api_base = provider_config.get('api_base')
        self.api_key = api_key
        self.model = model
        
        # Gemini特殊状态
        self._gemini_mode = None  # 'native' 或 'openai'
        
        logger.info(f"初始化 API 客户端: {self.provider_id} ({self.api_type}) - {self.model}")
    
    def generate_content(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: float = 1.0
    ) -> Dict[str, Any]:
        """
        生成内容（统一接口）
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            json_mode: 是否使用 JSON 模式
            temperature: 温度控制（0.0-2.0）
            
        Returns:
            Dict: 包含 'text' (响应文本), 'model' (使用的模型), 'usage' (Token 使用详情)
        """
        try:
            logger.debug(f"调用 {self.api_type} API: {self.model}")
            
            # 根据类型分发
            if self.api_type == 'openai':
                return self._call_openai(system_prompt, user_prompt, json_mode, temperature)
            elif self.api_type == 'anthropic':
                return self._call_anthropic(system_prompt, user_prompt, json_mode, temperature)
            elif self.api_type == 'gemini':
                return self._call_gemini(system_prompt, user_prompt, json_mode, temperature)
            else:
                raise ValueError(f"不支持的 API 类型: {self.api_type}")
                
        except Exception as e:
            logger.error(f"API 调用失败: {e}")
            raise
    
    
    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float
    ) -> Dict[str, Any]:
        """
        调用 OpenAI API（或兼容接口）
        """
        try:
            from openai import OpenAI
            from core.utils.llm_utils import retry_operation
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }
            
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            
            def _request():
                response = client.chat.completions.create(**kwargs)
                return {
                    'text': response.choices[0].message.content,
                    'model': response.model,
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    }
                }
                
            return retry_operation(_request, max_retries=3)
            
        except ImportError:
            raise Exception("openai 库未安装，请运行: pip install openai")
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise
    
    def _call_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float
    ) -> Dict[str, Any]:
        """
        调用 Anthropic Claude API
        """
        try:
            from anthropic import Anthropic
            from core.utils.llm_utils import retry_operation
            
            client = Anthropic(api_key=self.api_key)
            
            if json_mode:
                user_prompt += "\n\nPlease respond with valid JSON only, no markdown formatting."
            
            def _request():
                message = client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                return {
                    'text': message.content[0].text,
                    'model': message.model,
                    'usage': {
                        'prompt_tokens': message.usage.input_tokens,
                        'completion_tokens': message.usage.output_tokens,
                        'total_tokens': message.usage.input_tokens + message.usage.output_tokens
                    }
                }
                
            return retry_operation(_request, max_retries=3)
            
        except ImportError:
            raise Exception("anthropic 库未安装，请运行: pip install anthropic")
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            raise
    
    def _call_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float
    ) -> Dict[str, Any]:
        """
        调用 Google Gemini API - 自动检测模式
        """
        if self._gemini_mode == 'native':
            return self._call_gemini_native(system_prompt, user_prompt, json_mode, temperature)
        elif self._gemini_mode == 'openai':
            return self._call_gemini_openai(system_prompt, user_prompt, json_mode, temperature)
        
        # 首次调用：自动检测
        try:
            result = self._call_gemini_native(system_prompt, user_prompt, json_mode, temperature)
            self._gemini_mode = 'native'
            logger.info("✓ Gemini 原生 API 模式")
            return result
        except Exception as e1:
            logger.warning(f"Gemini 原生 API 失败: {e1}")
            try:
                result = self._call_gemini_openai(system_prompt, user_prompt, json_mode, temperature)
                self._gemini_mode = 'openai'
                logger.info("✓ Gemini OpenAI 兼容模式")
                return result
            except Exception as e2:
                raise Exception(f"Gemini API 调用失败\n原生: {str(e1)}\nOpenAI: {str(e2)}")
    
    def _call_gemini_native(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float
    ) -> Dict[str, Any]:
        """
        调用 Gemini 原生 API
        """
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.api_key)
            
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_prompt if system_prompt else None
            )
            
            if json_mode:
                config.response_mime_type = 'application/json'
            
            # 重试机制
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=[user_prompt],
                        config=config
                    )
                    
                    if response and response.text:
                        return {
                            'text': response.text,
                            'model': self.model,
                            'usage': {}
                        }
                    else:
                        raise Exception("Gemini 返回空响应")
                except Exception as e:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    raise
                    
        except ImportError:
            raise Exception("google-genai 库未安装，请运行: pip install google-genai")
        except Exception as e:
            raise Exception(f"Gemini 原生 API 错误: {str(e)}")
    
    def _call_gemini_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float
    ) -> Dict[str, Any]:
        """
        调用 Gemini OpenAI 兼容 API
        """
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base or "https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }
            
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            
            def _request():
                response = client.chat.completions.create(**kwargs)
                return {
                    'text': response.choices[0].message.content,
                    'model': response.model,
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    }
                }
            
            from core.utils.llm_utils import retry_operation
            return retry_operation(_request, max_retries=3)
            
        except ImportError:
            raise Exception("openai库未安装，请运行: pip install openai")
        except Exception as e:
            raise Exception(f"Gemini OpenAI 兼容 API 错误: {str(e)}")


# ========== 辅助函数 ==========

def load_providers_config(config_path: str = "config/providers.json") -> Dict[str, Dict]:
    """
    加载提供商配置文件
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        providers = {p['id']: p for p in data['providers']}
        logger.info(f"加载了 {len(providers)} 个 API 提供商")
        return providers
        
    except Exception as e:
        logger.error(f"加载提供商配置失败: {e}")
        return {}


def get_provider_models(provider_id: str, providers_config: Dict) -> List[str]:
    """获取指定提供商的模型列表"""
    if provider_id in providers_config:
        return providers_config[provider_id].get('models', [])
    return []


def get_models_with_cache(
    provider_id: str,
    provider_config: Dict,
    api_key: str,
    use_cache: bool = True
) -> List[str]:
    """
    获取模型列表（带缓存）
    """
    return provider_config.get('models', [])
