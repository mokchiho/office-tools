"""
文件类型校验工具 - 通过 Magic Bytes 验证文件真实类型
"""
import os
from pathlib import Path
from typing import Optional, Set

# 常见文件类型的 Magic Bytes 签名
# 格式: {扩展名: (魔数列表, MIME类型)}
FILE_SIGNATURES = {
    # 图片
    '.jpg': ([b'\xff\xd8\xff'], 'image/jpeg'),
    '.jpeg': ([b'\xff\xd8\xff'], 'image/jpeg'),
    '.png': ([b'\x89PNG\r\n\x1a\n'], 'image/png'),
    '.gif': ([b'GIF87a', b'GIF89a'], 'image/gif'),
    '.webp': ([b'RIFF'], 'image/webp'),
    '.bmp': ([b'BM'], 'image/bmp'),
    '.tiff': ([b'\x49\x49\x2a\x00', b'\x4d\x4d\x00\x2a'], 'image/tiff'),
    '.tif': ([b'\x49\x49\x2a\x00', b'\x4d\x4d\x00\x2a'], 'image/tiff'),
    # PDF
    '.pdf': ([b'%PDF'], 'application/pdf'),
    # Office 文档 (ZIP 格式)
    '.docx': ([b'PK\x03\x04'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    '.xlsx': ([b'PK\x03\x04'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    '.pptx': ([b'PK\x03\x04'], 'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
    '.odt': ([b'PK\x03\x04'], 'application/vnd.oasis.opendocument.text'),
    '.ods': ([b'PK\x03\x04'], 'application/vnd.oasis.opendocument.spreadsheet'),
    # 旧版 Office (MFC)
    '.doc': ([b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'], 'application/msword'),
    '.xls': ([b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'], 'application/vnd.ms-excel'),
    '.ppt': ([b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'], 'application/vnd.ms-powerpoint'),
    # 纯文本
    '.txt': (None, 'text/plain'),
    '.csv': (None, 'text/csv'),
    # 压缩文件
    '.zip': ([b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'], 'application/zip'),
    '.rar': ([b'Rar!\x1a\x07\x00'], 'application/x-rar-compressed'),
    '.7z': ([b'\x37\x7a\xbc\xaf\x27\x1c'], 'application/x-7z-compressed'),
}

# 支持的文件扩展名集合
ALLOWED_EXTENSIONS: Set[str] = set(FILE_SIGNATURES.keys())


def verify_file_signature(file_path: Path, expected_ext: str) -> dict:
    """
    验证文件的 Magic Bytes 是否与扩展名匹配
    
    参数:
        file_path: 文件路径
        expected_ext: 期望的扩展名（如 '.pdf'）
    
    返回:
        {"success": bool, "mime_type": str | None, "error": str | None}
    """
    expected_ext = expected_ext.lower()
    
    # 检查扩展名是否支持
    if expected_ext not in FILE_SIGNATURES:
        return {
            "success": False,
            "mime_type": None,
            "error": f"不支持的文件类型: {expected_ext}"
        }
    
    # 对于纯文本类型，不检查 Magic Bytes
    signatures, expected_mime = FILE_SIGNATURES[expected_ext]
    if signatures is None:
        # 尝试读取文件判断是否为有效文本
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                # 检查是否有空字节（通常是二进制文件）
                if b'\x00' in chunk:
                    return {
                        "success": False,
                        "mime_type": None,
                        "error": f"文件 {expected_ext} 应为纯文本格式"
                    }
            return {"success": True, "mime_type": expected_mime, "error": None}
        except Exception as e:
            return {"success": False, "mime_type": None, "error": f"读取文件失败: {e}"}
    
    # 检查文件大小（过小的文件可能是伪装的）
    file_size = file_path.stat().st_size
    if file_size < 4:
        return {
            "success": False,
            "mime_type": None,
            "error": "文件过小，无法验证类型"
        }
    
    # 读取文件头
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)
    except Exception as e:
        return {"success": False, "mime_type": None, "error": f"读取文件失败: {e}"}
    
    # 检查魔数
    for sig in signatures:
        if header.startswith(sig):
            return {"success": True, "mime_type": expected_mime, "error": None}
    
    # 特殊处理 WebP (RIFF....WEBP)
    if expected_ext == '.webp' and len(header) >= 12:
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return {"success": True, "mime_type": expected_mime, "error": None}
    
    return {
        "success": False,
        "mime_type": None,
        "error": f"文件内容与扩展名 {expected_ext} 不匹配，可能是伪造的文件"
    }


def verify_uploaded_file(file, allowed_exts: Set[str]) -> dict:
    """
    验证上传的文件（适用于 Flask request.files）
    
    参数:
        file: Flask FileStorage 对象
        allowed_exts: 允许的扩展名集合
    
    返回:
        {"success": bool, "error": str | None}
    """
    # 先检查扩展名
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        return {
            "success": False,
            "error": f"不支持的文件类型 {ext}，允许: {', '.join(sorted(allowed_exts))}"
        }
    
    # 检查文件大小
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    
    if size < 4:
        return {"success": False, "error": "文件过小，无法验证"}
    
    # 读取文件头
    header = file.read(32)
    file.seek(0)
    
    # 获取该扩展名对应的签名
    signatures = FILE_SIGNATURES.get(ext, (None, None))
    if signatures[0] is None:
        # 纯文本类型，简单检查是否有空字节
        if b'\x00' in header:
            return {"success": False, "error": f"文件 {ext} 应为文本格式"}
        return {"success": True, "error": None}
    
    # 检查魔数
    for sig in signatures[0]:
        if header.startswith(sig):
            return {"success": True, "error": None}
    
    # 特殊处理 WebP
    if ext == '.webp' and len(header) >= 12:
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return {"success": True, "error": None}
    
    return {
        "success": False,
        "error": f"文件内容与扩展名 {ext} 不匹配，可能是伪造的文件"
    }