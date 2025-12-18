import logging
import logging.handlers
import os
import sys
import json

def setup_logging(config_path=None):
    """
    配置全局日志
    """
    # 默认配置
    log_level_str = "INFO"
    log_file = "kaoche.log"
    
    # 尝试读取配置文件
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                log_level_str = settings.get('advanced', {}).get('log_level', 'INFO')
        except Exception as e:
            print(f"Error loading settings for logging: {e}")

    # 转换日志级别
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # 创建Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 获取根Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除旧的handlers，避免重复
    if root_logger.handlers:
        root_logger.handlers.clear()
        
    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 2. File Handler (Rotating)
    # 10MB per file, max 5 backups
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024, 
            backupCount=5, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}")
        
    logging.info(f"Log initialized. Level: {log_level_str}")
