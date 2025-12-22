"""
配置管理模块

支持配置的加载、保存和可选加密
"""

import json
import os
from typing import Dict, Any, Optional
import base64
import logging
from core.utils.utils import get_project_root

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器，支持加密敏感信息"""
    
    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            config_file = os.path.join(get_project_root(), 'config', 'settings.json')
        self.config_file = config_file
        self.config = {}
        self.encryption_enabled = False
        self._fernet = None
        self.password = None  # 内存密码缓存
        
    def load(self) -> Dict[str, Any]:
        """加载配置"""
        if not os.path.exists(self.config_file):
            logger.info("配置文件不存在，使用默认配置")
            return self._get_default_config()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            # 检查是否启用加密
            self.encryption_enabled = self.config.get('encryption', {}).get('enabled', False)
            
            logger.info(f"配置已加载 (加密: {'启用' if self.encryption_enabled else '禁用'})")
            return self.config
            
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._get_default_config()
    
    def save(self, config: Dict[str, Any]) -> bool:
        """保存配置"""
        try:
            self.config = config
            
            # 确保目录存在
            dirname = os.path.dirname(self.config_file)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            
            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info("配置已保存")
            return True
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def enable_encryption(self, password: str) -> bool:
        """
        启用加密
        
        Args:
            password: 主密码
            
        Returns:
            是否成功
        """
        try:
            self._fernet = self._create_fernet(password)
            self.encryption_enabled = True
            
            # 加密现有的API密钥
            if 'api' in self.config and 'api_key' in self.config['api']:
                plain_key = self.config['api']['api_key']
                if plain_key and not plain_key.startswith('enc:'):
                    encrypted_key = self._encrypt(plain_key)
                    self.config['api']['api_key'] = encrypted_key
            
            # 标记加密已启用
            if 'encryption' not in self.config:
                self.config['encryption'] = {}
            self.config['encryption']['enabled'] = True
            
            self.save(self.config)
            logger.info("加密已启用")
            return True
            
        except Exception as e:
            logger.error(f"启用加密失败: {e}")
            return False
    
    def disable_encryption(self, password: str) -> bool:
        """
        禁用加密
        
        Args:
            password: 主密码（用于解密现有数据）
            
        Returns:
            是否成功
        """
        try:
            # 验证密码并解密
            self._fernet = self._create_fernet(password)
            
            # 解密API密钥
            if 'api' in self.config and 'api_key' in self.config['api']:
                encrypted_key = self.config['api']['api_key']
                if encrypted_key and encrypted_key.startswith('enc:'):
                    plain_key = self._decrypt(encrypted_key)
                    self.config['api']['api_key'] = plain_key
            
            self.encryption_enabled = False
            self.config['encryption']['enabled'] = False
            self._fernet = None
            
            self.save(self.config)
            logger.info("加密已禁用")
            return True
            
        except Exception as e:
            logger.error(f"禁用加密失败（密码可能错误）: {e}")
            return False
    
    def get_api_key(self, password: Optional[str] = None, provider_id: Optional[str] = None) -> Optional[str]:
        """
        获取API密钥（自动解密）
        
        Args:
            password: 如果启用加密，需要提供密码
            provider_id: 可选的服务商ID
            
        Returns:
            API密钥明文
        """
        api_cfg = self.config.get('api', {})
        
        # 1. 优先从 providers 字典找
        api_key = ""
        if provider_id:
            api_key = api_cfg.get('keys', {}).get(provider_id, "")
        
        # 2. 兜底全局 key (如果特定 key 未找到)
        if not api_key:
            api_key = api_cfg.get('api_key', '')
            
        if not api_key:
            return None
        
        # 3. 检查是否加密
        if api_key.startswith('enc:'):
            if not password:
                logger.error("需要密码来解密API密钥")
                return None
            
            try:
                if not self._fernet:
                    self._fernet = self._create_fernet(password)
                return self._decrypt(api_key)
            except Exception as e:
                logger.error(f"解密API密钥失败: {e}")
                return None
        else:
            # 未加密
            return api_key
    
    def set_api_key(self, api_key: str, password: Optional[str] = None, provider_id: Optional[str] = None) -> bool:
        """
        设置API密钥（自动加密）
        
        Args:
            api_key: API密钥明文
            password: 如果启用加密，需要提供密码
            provider_id: 可选的服务商ID (LQA 规范)
            
        Returns:
            是否成功
        """
        try:
            if 'api' not in self.config:
                self.config['api'] = {}
            
            final_key = api_key
            # 如果启用加密
            if self.encryption_enabled:
                if not password:
                    logger.error("需要密码来加密API密钥")
                    return False
                
                if not self._fernet:
                    self._fernet = self._create_fernet(password)
                
                final_key = self._encrypt(api_key)
            
            # 存储位置分发
            if provider_id:
                if 'keys' not in self.config['api']:
                    self.config['api']['keys'] = {}
                self.config['api']['keys'][provider_id] = final_key
            else:
                self.config['api']['api_key'] = final_key
            
            return True
            
        except Exception as e:
            logger.error(f"设置API密钥失败: {e}")
            return False
    
    def _create_fernet(self, password: str):
        """
        从密码创建Fernet加密器
        """
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        except ImportError:
            raise RuntimeError("未检测到加密库！\n请在终端运行: pip install cryptography")

        # 使用固定的salt
        salt = b'kaoche_pro_salt_2024'
        
        # 使用PBKDF2HMAC从密码派生密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        
        return Fernet(key)
    
    def _encrypt(self, plain_text: str) -> str:
        """
        加密文本
        
        Args:
            plain_text: 明文
            
        Returns:
            加密后的文本（带enc:前缀）
        """
        if not self._fernet:
            raise ValueError("加密器未初始化")
        
        encrypted = self._fernet.encrypt(plain_text.encode())
        return 'enc:' + encrypted.decode()
    
    def _decrypt(self, encrypted_text: str) -> str:
        """
        解密文本
        
        Args:
            encrypted_text: 加密的文本（带enc:前缀）
            
        Returns:
            明文
        """
        if not self._fernet:
            raise ValueError("加密器未初始化")
        
        # 移除enc:前缀
        if encrypted_text.startswith('enc:'):
            encrypted_text = encrypted_text[4:]
        
        decrypted = self._fernet.decrypt(encrypted_text.encode())
        return decrypted.decode()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "api": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": ""
            },
            "ui": {
                "language": "zh_CN",
                "theme": "light",
                "font_size": 12
            },
            "advanced": {
                "batch_size": 10,
                "timeout": 30,
                "cache_ttl": 3600,
                "log_level": "INFO"
            },
            "encryption": {
                "enabled": False
            }
        }
    
    def verify_password(self, password: str) -> bool:
        """
        验证密码是否正确
        
        Args:
            password: 要验证的密码
            
        Returns:
            密码是否正确
        """
        try:
            fernet = self._create_fernet(password)
            
            # 尝试解密API密钥来验证密码
            api_key = self.config.get('api', {}).get('api_key', '')
            if api_key and api_key.startswith('enc:'):
                fernet.decrypt(api_key[4:].encode())
                return True
            else:
                # 如果没有加密数据，无法验证
                return True
                
        except Exception:
            return False


# 全局配置管理器实例
_config_manager = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager
