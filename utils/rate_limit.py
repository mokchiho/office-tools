"""
速率限制配置 - 使用 Flask-Limiter
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request

from config import RATE_LIMIT_DEFAULT, RATE_LIMIT_UPLOAD

# 获取真实 IP（考虑代理）
def get_real_ip():
    """从代理获取真实 IP"""
    # 检查 X-Forwarded-For 头
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # 取第一个 IP（原始客户端）
        return forwarded_for.split(',')[0].strip()
    
    # 检查 X-Real-IP 头
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # 降级使用远程地址
    return get_remote_address()


def init_limiter(app):
    """
    初始化速率限制器
    """
    limiter = Limiter(
        app=app,
        key_func=get_real_ip,  # 使用真实 IP 进行限流
        default_limits=[RATE_LIMIT_DEFAULT],
        storage_uri="memory://",  # 生产环境应使用 Redis
        strategy="fixed-window",
    )
    
    # 公开端点不受限流（可调整）
    # limiter.exempt("health")
    
    return limiter


# 预定义的限流规则
RATE_LIMITS = {
    'default': RATE_LIMIT_DEFAULT,
    'upload': RATE_LIMIT_UPLOAD,
    'ocr_start': '3 per minute',  # OCR 提交频率限制
    'ocr_poll': '60 per minute',  # OCR 状态查询可以频繁
}