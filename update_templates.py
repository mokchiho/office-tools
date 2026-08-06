#!/usr/bin/env python3
"""批量更新工具页面样式"""
import re
from pathlib import Path

TEMPLATES_DIR = Path("/home/mokch/projects/office-tools/templates")

# 工具页面分类映射
PAGE_CLASSES = {
    "pdf_to_word": "pdf-page",
    "pdf_merge": "pdf-page",
    "pdf_split": "pdf-page",
    "pdf_compress": "pdf-page",
    "pdf_watermark": "pdf-page",
    "pdf_encrypt": "pdf-page",
    "xls_to_xlsx": "excel-page",
    "csv_excel": "excel-page",
    "zh_convert": "excel-page",
    "image_compress": "image-page",
    "image_convert": "image-page",
    "images_to_pdf": "image-page",
    "hash_check": "code-page",
    "base64": "code-page",
    "json_tool": "code-page",
    "timestamp": "code-page",
    "qrcode": "qr-page",
}

# trust bar 内容映射
TRUST_BARS = {
    "pdf_to_word": [
        ("🔒", "服务器端处理"),
        ("📦", "最大 200MB"),
        ("⏱", "30分钟清理"),
    ],
    "pdf_merge": [
        ("🔒", "服务器端处理"),
        ("📦", "最多20个文件"),
        ("⏱", "30分钟清理"),
    ],
    "pdf_split": [
        ("🔒", "服务器端处理"),
        ("📦", "任意页数"),
        ("⏱", "30分钟清理"),
    ],
    "pdf_compress": [
        ("🔒", "服务器端处理"),
        ("📦", "最大 200MB"),
        ("⏱", "30分钟清理"),
    ],
    "pdf_watermark": [
        ("🔒", "服务器端处理"),
        ("📦", "最大 200MB"),
        ("⏱", "30分钟清理"),
    ],
    "pdf_encrypt": [
        ("🔒", "服务器端处理"),
        ("📦", "最大 200MB"),
        ("⏱", "30分钟清理"),
    ],
    "xls_to_xlsx": [
        ("🔒", "LibreOffice引擎"),
        ("📦", "最大 500MB"),
        ("⏱", "30分钟清理"),
    ],
    "csv_excel": [
        ("🔒", "服务器端处理"),
        ("📦", "编码自动检测"),
        ("⏱", "30分钟清理"),
    ],
    "zh_convert": [
        ("🔒", "OpenCC引擎"),
        ("📦", "6种格式支持"),
        ("⏱", "30分钟清理"),
    ],
    "image_compress": [
        ("🔒", "服务器端处理"),
        ("📦", "自定义质量"),
        ("⏱", "30分钟清理"),
    ],
    "image_convert": [
        ("🔒", "服务器端处理"),
        ("📦", "多格式支持"),
        ("⏱", "30分钟清理"),
    ],
    "images_to_pdf": [
        ("🔒", "服务器端处理"),
        ("📦", "最多10张"),
        ("⏱", "30分钟清理"),
    ],
    "hash_check": [
        ("🔒", "浏览器本地计算"),
        ("📦", "不上传服务器"),
        ("⏱", "即时完成"),
    ],
    "base64": [
        ("🔒", "浏览器本地处理"),
        ("📦", "不上传服务器"),
        ("⏱", "实时转换"),
    ],
    "json_tool": [
        ("🔒", "浏览器本地处理"),
        ("📦", "不上传服务器"),
        ("⏱", "即时完成"),
    ],
    "timestamp": [
        ("🔒", "浏览器本地处理"),
        ("📦", "不上传服务器"),
        ("⏱", "即时完成"),
    ],
    "qrcode": [
        ("🔒", "即时生成"),
        ("📦", "PNG/SVG下载"),
        ("⏱", "不保存数据"),
    ],
}

def update_tool_page(filepath, page_class, trust_items):
    """更新单个工具页面"""
    content = filepath.read_text(encoding="utf-8")

    # 1. 给 tool-page div 添加类别类
    content = content.replace(
        '<div class="tool-page">',
        f'<div class="tool-page {page_class}">',
        1  # 只替换第一个
    )

    # 2. 在 page-desc 后面插入 trust-bar
    trust_html = '\n        <div class="trust-bar">\n'
    for icon, text in trust_items:
        trust_html += f'            <span class="trust-bar-item">{icon} {text}</span>\n'
    trust_html += '        </div>\n'

    # 找到 page-desc 结束位置
    pattern = r'(<p class="page-desc">.*?</p>)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.end()] + trust_html + content[match.end():]

    # 3. 修复重复的 </section> 标签
    # 有些页面有多余的 </section> 结束标签
    content = re.sub(r'</section>\s*</section>\s*</div>\s*</body>', '</section>\n</div>\n\n', content)
    content = re.sub(r'</section>\s*</div>\s*</body>', '</section>\n</div>\n\n', content)

    filepath.write_text(content, encoding="utf-8")
    print(f"✓ Updated: {filepath.name}")


def main():
    for html_file in sorted(TEMPLATES_DIR.glob("*.html")):
        if html_file.name in ("index.html", "_seo.html", "_footer.html"):
            continue
        name = html_file.stem
        if name in PAGE_CLASSES:
            update_tool_page(
                html_file,
                PAGE_CLASSES[name],
                TRUST_BARS.get(name, [("🔒", "安全处理"), ("⏱", "30分钟清理")])
            )


if __name__ == "__main__":
    main()
