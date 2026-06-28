"""
办公工具集 - 转换函数单元测试
"""
import os
import sys
import tempfile
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image


# ── 页码范围解析测试 ──

def _parse_page_ranges(spec: str, total: int) -> list:
    """从 app.py 复制的测试用版本"""
    if not spec or not spec.strip():
        raise ValueError('页码范围不能为空')
    pages = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            segs = part.split('-', 1)
            try:
                a, b = int(segs[0].strip()), int(segs[1].strip())
            except ValueError:
                raise ValueError(f'无效页码范围: "{part}"')
            if a > b:
                a, b = b, a
            for p in range(a, b + 1):
                if p < 1 or p > total:
                    raise ValueError(f'页码 {p} 超出范围 (1-{total})')
                pages.add(p)
        else:
            try:
                p = int(part)
            except ValueError:
                raise ValueError(f'无效页码: "{part}"')
            if p < 1 or p > total:
                raise ValueError(f'页码 {p} 超出范围 (1-{total})')
            pages.add(p)
    if not pages:
        raise ValueError('未指定任何有效页码')
    return sorted(pages)


class TestParsePageRanges:
    """测试 _parse_page_ranges 函数"""

    def test_single_page(self):
        assert _parse_page_ranges("3", 10) == [3]

    def test_range(self):
        assert _parse_page_ranges("1-3", 10) == [1, 2, 3]

    def test_combined(self):
        assert _parse_page_ranges("1-3,5,7-9", 10) == [1, 2, 3, 5, 7, 8, 9]

    def test_reversed_range(self):
        assert _parse_page_ranges("5-3", 10) == [3, 4, 5]

    def test_all_pages(self):
        assert _parse_page_ranges("1-10", 10) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    def test_whitespace_handling(self):
        assert _parse_page_ranges(" 1 , 3-5 ", 10) == [1, 3, 4, 5]

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_page_ranges("", 10)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            _parse_page_ranges("11", 10)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            _parse_page_ranges("abc", 10)

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError):
            _parse_page_ranges("a-b", 10)

    def test_duplicates(self):
        assert _parse_page_ranges("1,1,2", 10) == [1, 2]


# ── 图片 MIME 测试 ──

def _image_mime(ext: str) -> str:
    _map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.webp': 'image/webp',
        '.bmp': 'image/bmp', '.gif': 'image/gif',
        '.tiff': 'image/tiff',
    }
    return _map.get(ext, 'application/octet-stream')


class TestImageMime:
    def test_jpg(self):
        assert _image_mime('.jpg') == 'image/jpeg'

    def test_png(self):
        assert _image_mime('.png') == 'image/png'

    def test_unknown_ext(self):
        assert _image_mime('.pdf') == 'application/octet-stream'

    def test_webp(self):
        assert _image_mime('.webp') == 'image/webp'


# ── 图片处理辅助测试 ──

class TestImagePrepare:
    def test_rgb_image_unchanged(self):
        img = Image.new('RGB', (100, 100), 'red')
        from app import _pil_prepare_for_jpeg
        result = _pil_prepare_for_jpeg(img)
        assert result.mode == 'RGB'

    def test_rgba_conversion(self):
        img = Image.new('RGBA', (100, 100), (255, 0, 0, 128))
        from app import _pil_prepare_for_jpeg
        result = _pil_prepare_for_jpeg(img)
        assert result.mode == 'RGB'


# ── 文件清理辅助测试 ──

class TestCleanup:
    def test_cleanup_nonexistent(self):
        from utils.cleanup import cleanup_file
        # cleanup_file should return False for non-existent files
        assert cleanup_file(Path('/tmp/nonexistent_file_xxx')) is False

    def test_cleanup_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = Path(f.name)
        assert tmp.exists()
        from utils.cleanup import cleanup_file
        assert cleanup_file(tmp) is True
        assert not tmp.exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
