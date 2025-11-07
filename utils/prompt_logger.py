"""
提示词日志记录模块
用于记录每个agent发送请求时的完整提示词
"""

import logging
import os
from datetime import datetime
from pathlib import Path


class PromptLogger:
    """提示词日志记录器"""
    
    def __init__(self, log_dir: str = "logs/prompts"):
        """
        初始化提示词日志记录器
        
        Args:
            log_dir: 日志文件存储目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建带时间戳的日志文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"prompts_{timestamp}.log"
        
        # 配置文件处理器
        self.file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        self.file_handler.setLevel(logging.INFO)
        
        # 设置格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s\n%(message)s\n' + '='*100
        )
        self.file_handler.setFormatter(formatter)
    
    def log_prompt(self, agent_name: str, prompt_type: str, prompt_content: str, metadata: dict = None):
        """
        记录提示词
        
        Args:
            agent_name: Agent名称
            prompt_type: 提示词类型(system/human/etc)
            prompt_content: 提示词内容
            metadata: 额外的元数据(例如:模型名称、温度等)
        """
        logger = logging.getLogger(f"PromptLogger.{agent_name}")
        
        # 如果logger还没有handler,添加file handler
        if not logger.handlers:
            logger.addHandler(self.file_handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        
        log_message = f"""
{'='*100}
Agent: {agent_name}
Prompt Type: {prompt_type}
Timestamp: {datetime.now().isoformat()}
{'='*100}

{prompt_content}

"""
        
        if metadata:
            log_message += f"\nMetadata: {metadata}\n"
        
        logger.info(log_message)
    
    def log_request_response(self, agent_name: str, request: dict, response: dict):
        """
        记录完整的请求和响应
        
        Args:
            agent_name: Agent名称
            request: 请求内容
            response: 响应内容
        """
        logger = logging.getLogger(f"PromptLogger.{agent_name}")
        
        if not logger.handlers:
            logger.addHandler(self.file_handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        
        log_message = f"""
{'='*100}
Agent: {agent_name}
Type: Request-Response Pair
Timestamp: {datetime.now().isoformat()}
{'='*100}

REQUEST:
{request}

RESPONSE:
{response}

"""
        logger.info(log_message)


# 全局提示词日志记录器实例
_global_prompt_logger = None


def get_prompt_logger(log_dir: str = "logs/prompts") -> PromptLogger:
    """获取全局提示词日志记录器实例"""
    global _global_prompt_logger
    if _global_prompt_logger is None:
        _global_prompt_logger = PromptLogger(log_dir=log_dir)
    return _global_prompt_logger


def log_agent_prompt(agent_name: str, prompt_type: str, prompt_content: str, metadata: dict = None):
    """
    便捷函数:记录agent提示词
    
    Args:
        agent_name: Agent名称
        prompt_type: 提示词类型
        prompt_content: 提示词内容
        metadata: 额外元数据
    """
    logger = get_prompt_logger()
    logger.log_prompt(agent_name, prompt_type, prompt_content, metadata)
