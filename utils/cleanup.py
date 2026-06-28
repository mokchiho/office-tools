"""
文件清理工具 - 定时清理过期文件
"""
import os
import time
import threading
import shutil
from pathlib import Path
from typing import List

from config import UPLOAD_DIR, OUTPUT_DIR, CLEANUP_INTERVAL, FILE_EXPIRE_SECONDS
from utils.logging_config import get_logger

logger = get_logger(__name__)

# 清理锁
_cleanup_lock = threading.Lock()
_last_cleanup_time = time.time()


def cleanup_file(path: Path) -> bool:
    """删除文件或目录"""
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
            logger.debug(f"已删除文件: {path}")
            return True
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            logger.debug(f"已删除目录: {path}")
            return True
    except Exception as e:
        logger.error(f"删除失败 {path}: {e}")
    return False


def get_all_temp_dirs() -> List[Path]:
    """获取所有临时文件目录"""
    dirs = []
    if UPLOAD_DIR.exists():
        dirs.append(UPLOAD_DIR)
    if OUTPUT_DIR.exists():
        dirs.append(OUTPUT_DIR)
    return dirs


def cleanup_expired_files() -> dict:
    """
    清理超过过期时间的文件
    返回: {"deleted": 数量, "errors": 数量}
    """
    global _last_cleanup_time
    
    now = time.time()
    
    # 节流：避免频繁清理
    with _cleanup_lock:
        if now - _last_cleanup_time < CLEANUP_INTERVAL:
            return {"deleted": 0, "errors": 0, "skipped": "too soon"}
        _last_cleanup_time = now
    
    cutoff = now - FILE_EXPIRE_SECONDS
    deleted = 0
    errors = 0
    
    for temp_dir in get_all_temp_dirs():
        if not temp_dir.exists():
            continue
            
        for item in temp_dir.iterdir():
            try:
                # 只处理文件（不处理目录）
                if not item.is_file():
                    continue
                    
                mtime = item.stat().st_mtime
                if mtime < cutoff:
                    if cleanup_file(item):
                        deleted += 1
                    else:
                        errors += 1
                        
            except Exception as e:
                logger.error(f"检查文件 {item} 时出错: {e}")
                errors += 1
    
    if deleted > 0 or errors > 0:
        logger.info(f"清理完成: 删除 {deleted} 个文件, 错误 {errors} 个")
    
    return {"deleted": deleted, "errors": errors}


def cleanup_orphaned_ocr_tasks() -> int:
    """
    清理孤立的 OCR 任务（无对应任务状态但文件存在）
    """
    if not OUTPUT_DIR.exists():
        return 0
    
    orphaned = 0
    for item in OUTPUT_DIR.glob('_ocr_*'):
        try:
            if item.is_file():
                # 检查文件是否过期（超过 30 分钟）
                mtime = item.stat().st_mtime
                if time.time() - mtime > FILE_EXPIRE_SECONDS:
                    if cleanup_file(item):
                        orphaned += 1
        except Exception as e:
            logger.error(f"清理孤立 OCR 文件 {item} 时出错: {e}")
    
    return orphaned


def cleanup_startup() -> dict:
    """
    启动时清理：删除所有临时文件
    返回: {"deleted": 数量}
    """
    deleted = 0
    for temp_dir in get_all_temp_dirs():
        if not temp_dir.exists():
            continue
            
        for item in temp_dir.iterdir():
            try:
                if cleanup_file(item):
                    deleted += 1
            except Exception as e:
                logger.error(f"启动清理 {item} 时出错: {e}")
    
    logger.info(f"启动清理完成: 删除 {deleted} 个残留文件")
    return {"deleted": deleted}


def cleanup_scheduled():
    """定时清理任务（供 after_request 钩子调用）"""
    try:
        result = cleanup_expired_files()
        if result.get("deleted", 0) > 0:
            logger.debug(f"定时清理: {result}")
    except Exception as e:
        logger.error(f"定时清理失败: {e}")