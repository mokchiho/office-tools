"""
日志配置模块 - 统一的日志配置
"""
import logging
import sys
from pathlib import Path
from colorlog import ColoredFormatter

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 日志目录
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 日志文件路径
APP_LOG_FILE = LOG_DIR / 'app.log'
ERROR_LOG_FILE = LOG_DIR / 'error.log'


def setup_logging(log_level='INFO'):
    """
    配置日志系统
    - 控制台输出：带颜色的简洁格式
    - 文件输出：详细格式 + 分离错误日志
    """
    # 移除默认 handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # ── 控制台 Handler ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    console_formatter = ColoredFormatter(
        '%(log_color)s[%(levelname)s]%(reset)s %(message)s',
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    
    # ── 通用文件 Handler ──
    file_handler = logging.FileHandler(APP_LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # ── 错误专用 Handler ──
    error_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    
    # ── 配置根 Logger ──
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    return root_logger


# 预定义的 logger
def get_logger(name: str) -> logging.Logger:
    """获取业务 logger"""
    return logging.getLogger(name)


# 初始化日志系统
logger = setup_logging()