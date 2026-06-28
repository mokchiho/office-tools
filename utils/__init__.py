"""
办公效率工具集 - 核心模块
"""
__version__ = '1.0.0'
__author__ = '办公效率工具集'

from config import (
    BASE_DIR,
    UPLOAD_DIR,
    OUTPUT_DIR,
    SITE_URL,
    SITE_NAME,
    MAX_CONTENT_LENGTH,
    SEO_META,
)

# 导入工具模块
from utils.logging_config import get_logger, setup_logging
from utils.cleanup import cleanup_expired_files, cleanup_startup
from utils.download import make_download_response, make_json_response
from utils.rate_limit import init_limiter, RATE_LIMITS

__all__ = [
    '__version__',
    'BASE_DIR',
    'UPLOAD_DIR', 
    'OUTPUT_DIR',
    'SITE_URL',
    'SITE_NAME',
    'MAX_CONTENT_LENGTH',
    'SEO_META',
    'get_logger',
    'setup_logging',
    'cleanup_expired_files',
    'cleanup_startup',
    'make_download_response',
    'make_json_response',
    'init_limiter',
    'RATE_LIMITS',
]