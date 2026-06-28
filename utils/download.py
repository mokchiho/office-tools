"""
下载响应工具 - 统一构造下载响应，自动清理临时文件
"""
import os
from pathlib import Path
from typing import Optional

from flask import send_file, jsonify, Response

from config import UPLOAD_DIR, OUTPUT_DIR
from utils.cleanup import cleanup_file
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DownloadResponse:
    """
    下载响应构建器
    - 自动处理文件存在性检查
    - 下载完成后自动清理源文件和目标文件
    - 支持自定义文件名
    """
    
    def __init__(
        self,
        dst_path: Path,
        src_path: Optional[Path] = None,
        download_name: Optional[str] = None,
        mime_type: str = 'application/octet-stream',
        cleanup_dst: bool = True,
        cleanup_src: bool = True,
    ):
        self.dst_path = dst_path
        self.src_path = src_path
        self.download_name = download_name
        self.mime_type = mime_type
        self.cleanup_dst = cleanup_dst
        self.cleanup_src = cleanup_src
    
    def _cleanup(self):
        """清理相关文件"""
        if self.cleanup_dst and self.dst_path and self.dst_path.exists():
            cleanup_file(self.dst_path)
        if self.cleanup_src and self.src_path and self.src_path.exists():
            cleanup_file(self.src_path)
    
    def as_response(self) -> Response:
        """生成 Flask 响应"""
        # 检查输出文件是否存在
        if not self.dst_path.exists():
            logger.warning(f"输出文件不存在: {self.dst_path}")
            return jsonify(success=False, error='输出文件不存在'), 500
        
        # 检查文件是否为空
        if self.dst_path.stat().st_size == 0:
            logger.warning(f"输出文件为空: {self.dst_path}")
            cleanup_file(self.dst_path)
            return jsonify(success=False, error='输出文件为空'), 500
        
        # 构建响应
        resp = send_file(
            str(self.dst_path),
            as_attachment=True,
            download_name=self.download_name,
            mimetype=self.mime_type,
        )
        
        # 注册下载完成后的清理回调
        @resp.call_on_close
        def _cleanup_on_close():
            self._cleanup()
            logger.debug(f"下载完成并清理: {self.dst_path}")
        
        return resp


def make_download_response(
    dst_path: Path,
    src_path: Optional[Path] = None,
    original_filename: str = '',
    new_ext: str = '',
    mime_type: str = 'application/octet-stream',
) -> Response:
    """
    便捷函数：构造下载响应
    
    参数:
        dst_path: 输出文件路径
        src_path: 输入文件路径（可选，用于下载后清理）
        original_filename: 原始文件名（用于生成下载名）
        new_ext: 新文件扩展名（如 '.pdf'）
        mime_type: MIME 类型
    
    示例:
        return make_download_response(
            dst_path=dst_path,
            src_path=src_path,
            original_filename=file.filename,
            new_ext='.pdf',
            mime_type='application/pdf',
        )
    """
    # 生成下载名
    if original_filename:
        stem = Path(original_filename).stem
    else:
        stem = 'download'
    
    download_name = f"{stem}{new_ext}"
    
    return DownloadResponse(
        dst_path=dst_path,
        src_path=src_path,
        download_name=download_name,
        mime_type=mime_type,
    ).as_response()


def make_json_response(success: bool, **kwargs):
    """
    便捷函数：构造 JSON 响应
    自动处理 error 状态码
    """
    if not success:
        error_msg = kwargs.get('error', '未知错误')
        status_code = kwargs.get('status_code', 500)
        return jsonify(success=False, error=error_msg), status_code
    
    # 移除多余的 status_code
    kwargs.pop('status_code', None)
    return jsonify(success=True, **kwargs)