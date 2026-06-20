"""批量改造 16 个工具页 — 注入 SEO 元素。

v3 策略: 自我修复模式。
不论起始状态是 HEAD 原版, 还是被旧脚本污染, 都能修复并注入。
"""
import re
from pathlib import Path

ROOT = Path("/home/mokch/projects/office-tools")
TMPL = ROOT / "templates"

TOOL_PAGES = [
    ("xls_to_xlsx",   "xls_to_xlsx.html",   True,  ["csv-excel", "pdf-merge", "image-compress", "json-tool"]),
    ("pdf_to_word",   "pdf_to_word.html",   True,  ["pdf-merge", "pdf-split", "pdf-compress", "pdf-encrypt"]),
    ("image_compress","image_compress.html",False,  ["image-convert", "images-to-pdf", "pdf-compress", "base64"]),
    ("image_convert", "image_convert.html", False,  ["image-compress", "images-to-pdf", "pdf-to-word", "qrcode"]),
    ("images_to_pdf", "images_to_pdf.html", False,  ["pdf-merge", "pdf-compress", "image-compress", "image-convert"]),
    ("hash_check",    "hash_check.html",    False,  ["base64", "json-tool", "timestamp", "pdf-encrypt"]),
    ("base64",        "base64.html",        False,  ["json-tool", "hash-check", "timestamp", "qrcode"]),
    ("json_tool",     "json_tool.html",     False,  ["base64", "timestamp", "hash-check", "csv-excel"]),
    ("timestamp",     "timestamp.html",     False,  ["json-tool", "base64", "qrcode", "hash-check"]),
    ("pdf_merge",     "pdf_merge.html",     False,  ["pdf-split", "pdf-compress", "pdf-to-word", "pdf-watermark"]),
    ("pdf_split",     "pdf_split.html",     False,  ["pdf-merge", "pdf-compress", "pdf-to-word", "pdf-watermark"]),
    ("pdf_compress",  "pdf_compress.html",  False,  ["pdf-merge", "pdf-split", "image-compress", "pdf-watermark"]),
    ("qrcode",        "qrcode.html",        False,  ["base64", "image-convert", "timestamp", "json-tool"]),
    ("pdf_watermark", "pdf_watermark.html", False,  ["pdf-encrypt", "pdf-merge", "pdf-compress", "images-to-pdf"]),
    ("pdf_encrypt",   "pdf_encrypt.html",   False,  ["pdf-watermark", "pdf-compress", "pdf-merge", "hash-check"]),
    ("csv_excel",     "csv_excel.html",     False,  ["xls-to-xlsx", "json-tool", "pdf-merge", "timestamp"]),
]

FAQ = {
    "xls_to_xlsx": [
        ("XLS 和 XLSX 有什么区别?", "XLS 是 Excel 97-2003 的旧版二进制格式,最大支持 65536 行;XLSX 是 Excel 2007+ 启用的现代 XML 格式,支持 1048576 行,文件更小且支持更多新功能。"),
        ("XLS 转 XLSX 会丢失格式吗?", "不会。本工具基于 LibreOffice 引擎,完整保留单元格格式、字体、颜色、图片、图表、公式等所有元素。"),
        ("最大支持多大的文件?", "单文件最大 500MB,转换基于 LibreOffice 本地引擎,处理速度快。"),
        ("我的文件安全吗?", "文件仅用于本次转换,不会永久存储。所有临时文件 30 分钟后自动清理。"),
    ],
    "pdf_to_word": [
        ("PDF 转 Word 后可以编辑吗?", "可以。转换后输出为标准 DOCX 格式,可在 Microsoft Word、WPS、LibreOffice 等任意文字处理软件中自由编辑。"),
        ("支持扫描件 PDF 吗?", "支持。本工具集成 PP-OCRv6 OCR 引擎,可识别扫描件中的文字并转换为可编辑文本。"),
        ("会保留原 PDF 的排版吗?", "会。pdf2docx 引擎会尽力保留原始排版,包括段落、表格、字体、图片、超链接等元素。"),
        ("最大支持多大的 PDF?", "单文件最大 200MB。超大文件建议先用 PDF 压缩工具减小体积。"),
    ],
    "image_compress": [
        ("图片压缩会降低画质吗?", "会有轻微降低。本工具提供 0-100% 质量滑块,建议设置 70-85% 即可在保持视觉质量的同时大幅减小体积。"),
        ("支持哪些图片格式?", "支持 JPG/JPEG、PNG、WebP 三种主流格式。推荐 JPG 用于照片,PNG 用于透明背景,WebP 用于现代应用。"),
        ("最大支持多大的图片?", "单张图片最大 50MB。建议先用图片格式转换工具调整尺寸再压缩,以获得最佳效果。"),
        ("可以批量压缩多张图片吗?", "支持。可以一次选择多张图片,工具会逐张压缩并分别提供下载。"),
    ],
    "image_convert": [
        ("支持哪些图片格式互转?", "支持 JPG/PNG/WebP/BMP/GIF/TIFF 六种格式互转。所有转换均在本地完成,不上传服务器。"),
        ("转换后图片质量会变化吗?", "JPG/WebP 转换时可设置质量参数(0-100%),默认 90% 几乎无损;PNG/BMP/TIFF 为无损格式,转换不损失质量。"),
        ("GIF 动图转换后会动吗?", "仅保留第一帧。如需保留动画请使用其他动图工具。"),
        ("最大支持多大的图片?", "单张图片最大 50MB,转换基于 Pillow 本地库处理。"),
    ],
    "images_to_pdf": [
        ("可以放多少张图片?", "最多支持 10 张图片,每张图片将作为 PDF 的一页,按上传顺序排列。"),
        ("可以调整图片顺序吗?", "可以。上传后可拖拽卡片调整顺序,转换后 PDF 将按调整后的顺序输出。"),
        ("支持哪些图片格式?", "支持 JPG/PNG/WebP 三种主流格式,不同格式可混合上传。"),
        ("PDF 分辨率是多少?", "默认 A4 纸张大小,图片自动缩放适应页面,保持原始比例。"),
    ],
    "hash_check": [
        ("MD5/SHA1/SHA256 有什么区别?", "MD5 速度快但安全性低(已不推荐用于安全);SHA1 比 MD5 安全但也已被攻破;SHA256/SHA512 是目前推荐的安全标准,广泛用于文件完整性验证。"),
        ("我的文件会上传服务器吗?", "不会。本工具使用浏览器端 Web Crypto API 进行计算,文件始终在您的设备上,完全保护隐私。"),
        ("哈希值有什么用途?", "用于验证文件完整性(下载后哈希一致说明未被篡改)、校验文件唯一性、密码存储等场景。"),
        ("最大支持多大的文件?", "支持任意大小文件,本地流式计算,不占用服务器资源。"),
    ],
    "base64": [
        ("Base64 是什么?", "Base64 是一种基于 64 个可打印字符来表示二进制数据的编码方式,常用于在 URL、Cookie、JSON 中传递二进制数据。"),
        ("支持中文编码吗?", "支持。本工具使用 UTF-8 编码处理中文,可正确编码/解码包含中文、表情符号等任意 Unicode 字符。"),
        ("数据会上传服务器吗?", "不会。所有处理完全在浏览器本地完成,数据不会离开您的设备。"),
        ("有长度限制吗?", "无硬性限制,但建议单次输入不超过 10MB 文本以保证浏览器性能。"),
    ],
    "json_tool": [
        ("JSON 格式化有什么用途?", "将压缩的 JSON 字符串(单行)美化为带缩进的多行格式,便于阅读和调试;压缩则相反,可减小传输体积。"),
        ("能定位错误位置吗?", "可以。当 JSON 不合法时,工具会高亮显示错误所在的行列号,并提示错误原因。"),
        ("支持 JSON5 或注释吗?", "不支持。严格的 JSON5/带注释 JSON 需要先转换为标准 JSON 才能被服务器解析。"),
        ("我的数据安全吗?", "完全本地处理,不会上传到服务器。可放心处理敏感数据。"),
    ],
    "timestamp": [
        ("什么是 Unix 时间戳?", "Unix 时间戳是从 1970-01-01 00:00:00 UTC 起的秒数(或毫秒数),广泛用于程序和数据库中表示时间。"),
        ("支持秒和毫秒吗?", "支持。自动识别 10 位(秒)和 13 位(毫秒)时间戳,转换结果中可一键复制两种格式。"),
        ("时区是什么?", "默认显示北京时间(UTC+8)。如需其他时区请在结果中手动调整。"),
        ("支持负数时间戳吗?", "支持。负数时间戳表示 1970 年之前的时间,可正常解析。"),
    ],
    "pdf_merge": [
        ("PDF 合并的顺序如何调整?", "上传文件后,可通过拖拽文件卡片调整合并顺序,文件将按从上到下的顺序拼接。"),
        ("最多能合并多少个文件?", "最多支持 20 个 PDF 文件同时合并,总大小不超过 200MB。"),
        ("会保留书签吗?", "会。本工具会保留原 PDF 中的书签和元数据,合并后仍可使用。"),
        ("输出格式是什么?", "输出标准 PDF 格式,兼容所有 PDF 阅读器。"),
    ],
    "pdf_split": [
        ("支持哪些拆分方式?", "支持单页提取、多页提取、按页码范围(如 1-3,5,7-9)拆分,可灵活组合。"),
        ("拆分后每个 PDF 大小?", "拆分后的 PDF 仅包含指定的页面,文件大小相应减小。"),
        ("最大支持多大的 PDF?", "单文件最大 200MB,处理基于 PyPDF2 库,速度快。"),
        ("会保留原始质量吗?", "会。拆分不会重新编码,完全保留原始 PDF 的内容、字体、图片质量。"),
    ],
    "pdf_compress": [
        ("PDF 压缩的原理是什么?", "通过降低 PDF 中图片的分辨率(DPI)和质量来减小体积,适合扫描件型 PDF。文字内容本身已高度压缩,不会损失。"),
        ("三档压缩有什么区别?", "轻度(150 DPI)质量保留最好,适合打印;中度(120 DPI)平衡;激进(72 DPI)体积最小,适合屏幕阅读。"),
        ("文字型 PDF 能压缩吗?", "文字型 PDF 本身已高度压缩,空间有限(通常 10-30%)。本工具对扫描件型 PDF 效果最显著。"),
        ("最大支持多大的 PDF?", "单文件最大 200MB,处理基于 pikepdf 库。"),
    ],
    "qrcode": [
        ("支持哪些类型二维码?", "支持纯文本、网址 URL、WiFi 配置(自动连接)、电子邮箱(自动发邮件)、电话号码(自动拨号)等多种类型。"),
        ("PNG 和 SVG 有什么区别?", "PNG 是位图,适合屏幕显示和照片;SVG 是矢量图,可无限放大不失真,适合印刷和高质量场景。"),
        ("二维码会过期吗?", "本工具生成的二维码是静态的,内容由您输入,不会过期失效,无需联网即可扫描。"),
        ("可以自定义颜色吗?", "可以。支持自定义前景色和背景色,生成的二维码仍可被所有扫码软件识别。"),
    ],
    "pdf_watermark": [
        ("水印是平铺的吗?", "是的,默认对角线平铺,覆盖整个页面,既起到保护作用又不影响阅读。"),
        ("可以自定义水印吗?", "可以自定义文字、字体、大小、颜色、透明度、旋转角度等参数。"),
        ("水印能被去除吗?", "本工具生成的是平铺水印,无法被简单的编辑去除。如需更高级保护请配合 PDF 加密使用。"),
        ("支持中文水印吗?", "支持。可输入任意 Unicode 字符,包括中文、表情符号等。"),
    ],
    "pdf_encrypt": [
        ("加密后忘记密码怎么办?", "很遗憾,AES 256 加密强度下忘记密码无法恢复。请妥善保管密码或备份未加密的原始文件。"),
        ("用户密码和所有者密码的区别?", "用户密码:打开 PDF 时需要输入;所有者密码:仅限制编辑/打印/复制等操作,可正常打开查看。"),
        ("解密需要原密码吗?", "是的,解密必须知道原密码(所有者密码)才能移除限制,这是出于安全考虑。"),
        ("加密算法是什么?", "采用 AES-256 强加密,符合 PDF 2.0 标准,兼容所有现代 PDF 阅读器。"),
    ],
    "csv_excel": [
        ("中文乱码怎么解决?", "本工具自动检测文件编码(UTF-8/GBK/GB2312 等),可彻底解决 Excel 打开 CSV 时的中文乱码问题。"),
        ("支持自定义分隔符吗?", "支持。可选择逗号、分号、Tab、空格等常用分隔符,适配各种数据源。"),
        ("Excel 转 CSV 时会丢失格式吗?", "CSV 本身是纯文本格式,只保留数据内容(不保留颜色、公式等格式)。如需保留请用 XLSX 输出。"),
        ("支持大型 CSV 文件吗?", "单文件最大 50MB,处理基于 Pandas 库,百万行级数据处理流畅。"),
    ],
}

SLUG_PATH = {
    "xls-to-xlsx": "/xls-to-xlsx", "pdf-to-word": "/pdf-to-word",
    "image-compress": "/image-compress", "image-convert": "/image-convert",
    "images-to-pdf": "/images-to-pdf", "hash-check": "/hash-check",
    "base64": "/base64", "json-tool": "/json-tool", "timestamp": "/timestamp",
    "pdf-merge": "/pdf-merge", "pdf-split": "/pdf-split",
    "pdf-compress": "/pdf-compress", "qrcode": "/qrcode",
    "pdf-watermark": "/pdf-watermark", "pdf-encrypt": "/pdf-encrypt",
    "csv-excel": "/csv-excel",
}
SLUG_LABEL = {
    "xls-to-xlsx": "XLS 转 XLSX", "pdf-to-word": "PDF 转 Word",
    "image-compress": "图片压缩", "image-convert": "图片格式转换",
    "images-to-pdf": "图片转 PDF", "hash-check": "文件哈希校验",
    "base64": "Base64 编解码", "json-tool": "JSON 格式化", "timestamp": "时间戳转换",
    "pdf-merge": "PDF 合并", "pdf-split": "PDF 拆分",
    "pdf-compress": "PDF 压缩", "qrcode": "二维码生成",
    "pdf-watermark": "PDF 加水印", "pdf-encrypt": "PDF 加密/解密",
    "csv-excel": "CSV ↔ Excel",
}
SLUG_ICON = {
    "xls-to-xlsx": "📊", "pdf-to-word": "📄",
    "image-compress": "🖼️", "image-convert": "🔄",
    "images-to-pdf": "📑", "hash-check": "🔐",
    "base64": "🔤", "json-tool": "{ }", "timestamp": "⏱",
    "pdf-merge": "📚", "pdf-split": "✂️",
    "pdf-compress": "📦", "qrcode": "📱",
    "pdf-watermark": "💧", "pdf-encrypt": "🔒",
    "csv-excel": "🔄",
}


def head_block(slug: str, has_common_js: bool) -> str:
    common_js = '    <script src="{{ url_for(\'static\', filename=\'common.js\') }}"></script>\n' if has_common_js else ''
    return f"""<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{{{ seo_meta.{slug}.title }}}}</title>
    {{% import '_seo.html' as seo_macros %}}
    {{{{ seo_macros.head(
        title=seo_meta.{slug}.title,
        description=seo_meta.{slug}.description,
        keywords=seo_meta.{slug}.keywords,
        path=seo_meta.{slug}.path,
        jsonld_type='WebApplication'
    ) }}}}
    {{{{ seo_macros.breadcrumb([
        {{'name': '首页', 'url': '/'}},
        {{'name': seo_meta.{slug}.title.split(' - ')[0], 'url': seo_meta.{slug}.path}}
    ]) }}}}
    <link rel="stylesheet" href="{{{{ url_for('static', filename='style.css') }}}}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{common_js}</head>"""


def faq_jsonld_block(slug: str) -> str:
    qas = FAQ[slug]
    items = []
    for q, a in qas:
        # 使用 json.dumps 保证双引号 + 正确转义
        import json as _json
        q_json = _json.dumps(q, ensure_ascii=False)
        a_json = _json.dumps(a, ensure_ascii=False)
        items.append(
            "        {\n"
            "          \"@type\": \"Question\",\n"
            f"          \"name\": {q_json},\n"
            "          \"acceptedAnswer\": {\n"
            "            \"@type\": \"Answer\",\n"
            f"            \"text\": {a_json}\n"
            "          }\n"
            "        }"
        )
    items_str = ",\n".join(items)
    return (
        '<script type="application/ld+json">\n'
        '{\n'
        '  "@context": "https://schema.org",\n'
        '  "@type": "FAQPage",\n'
        f'  "mainEntity": [\n{items_str}\n  ]\n'
        '}\n'
        '</script>'
    )


def related_tools_block(related: list) -> str:
    cards = []
    for rs in related:
        cards.append(
            f'        <a href="{SLUG_PATH[rs]}" class="related-tool-card">\n'
            f'            <span class="related-tool-icon">{SLUG_ICON[rs]}</span>\n'
            f'            <span class="related-tool-name">{SLUG_LABEL[rs]}</span>\n'
            f'        </a>'
        )
    cards_str = "\n".join(cards)
    return (
        '<section class="related-tools" aria-label="相关工具">\n'
        '    <h2>🔗 相关工具</h2>\n'
        '    <div class="related-tools-grid">\n'
        f'{cards_str}\n'
        '    </div>\n'
        '</section>'
    )


# ── 自我修复: 把任何被旧脚本污染的状态还原到原版 ──
def repair_to_original(html: str, slug: str) -> str:
    """把 html 还原到 HEAD 原版状态。

    处理以下污染:
    1. <h3>使用说明</h3> (旧脚本可能已替换)
    2. <section class="faq"> 包装
    3. .note 后的多余 </div> 和 </section>
    4. FAQPage JSON-LD
    5. related-tools section
    6. _footer.html include
    """

    # 1. 恢复 H3 文本 (针对 xls_to_xlsx 特殊处理)
    target_h3 = '<h3>📋 说明</h3>' if slug == 'xls_to_xlsx' else '<h3>📋 使用说明</h3>'
    html = re.sub(
        r'<h3>使用说明</h3>',
        target_h3,
        html,
    )
    # 2. 移除 <section class="faq"> 开头包装 + H2
    #    模式: [空白]<section class="faq">[内容]…[空白]<div class="note">
    #    删除 section 和 h2 标签, 保留 <div class="note">
    html = re.sub(
        r'<section class="faq">\s*<h2>❓\s*常见问题</h2>\s*<div class="note">',
        '<div class="note">',
        html,
        flags=re.S,
    )
    # 3. 移除 .note 结束 </div> 之后的多余 </div> + </section>
    #    模式: </div>[空白]</div>[空白]</section>
    #    替换为 </div> (保留 .note 自己的 </div>)
    html = re.sub(
        r'</div>\s*</div>\s*</section>',
        '</div>',
        html,
    )
    # 4. 移除 FAQPage JSON-LD
    html = re.sub(
        r'\s*<script type="application/ld\+json">\s*\{\s*"@context":\s*"https://schema\.org",\s*"@type":\s*"FAQPage".*?</script>\s*',
        '\n',
        html,
        flags=re.S,
    )
    # 5. 移除 related-tools section
    html = re.sub(
        r'\s*<section class="related-tools".*?</section>\s*',
        '\n',
        html,
        flags=re.S,
    )
    # 6. 移除 _footer.html include
    html = re.sub(
        r'\s*\{%\s*include\s+\'_footer\.html\'\s*%\}\s*',
        '\n    ',
        html,
    )
    # 7. 移除 site-footer 已渲染的版本 (如果曾被 _footer.html 渲染过)
    html = re.sub(
        r'\s*<footer class="site-footer".*?</footer>\s*',
        '\n',
        html,
        flags=re.S,
    )

    # 8. .note 内 H3 已经是 📋 emoji 的原版, 不再处理

    return html


def transform(slug: str, tpl: str, has_common_js: bool, related: list) -> None:
    p = TMPL / tpl
    html = p.read_text(encoding="utf-8")

    # 0. 修复 (把任何状态还原到原版)
    html = repair_to_original(html, slug)

    # 1. 替换 <head>...</head>
    new_head = head_block(slug, has_common_js)
    html = re.sub(r"<head>.*?</head>", new_head, html, count=1, flags=re.S)

    # 2. .note 标题统一为 <h3>使用说明</h3> (去 emoji, 为 SEO 结构清晰)
    html = re.sub(r"<h3>📋\s*使用说明</h3>", "<h3>使用说明</h3>", html)
    html = re.sub(r"<h3>📋\s*说明</h3>", "<h3>使用说明</h3>", html)

    # 3. 在 <div class="note"> 前注入 H2 标题
    html = html.replace(
        '<div class="note">',
        '<section class="faq">\n'
        '            <h2>❓ 常见问题</h2>\n'
        '            <div class="note">',
        1,
    )

    # 4. 找到 <div class="note">...</div> 完整块, 在其后注入 section close + FAQPage + related tools
    note_match = re.search(r'(<div class="note">.*?</div>)', html, re.S)
    if note_match:
        injection = (
            '\n            </section>\n\n'
            '            ' + faq_jsonld_block(slug) + '\n\n'
            '            ' + related_tools_block(related) + '\n'
            '        '
        )
        html = html[:note_match.end()] + injection + html[note_match.end():]

    # 5. 在 </body> 之前注入页脚
    html = re.sub(
        r"</body>\s*</html>\s*$",
        "\n    {% include '_footer.html' %}\n</body>\n</html>\n",
        html,
    )

    p.write_text(html, encoding="utf-8")


def main():
    for slug, tpl, has_cjs, related in TOOL_PAGES:
        transform(slug, tpl, has_cjs, related)
        print(f"  ✓ {tpl}")
    print(f"\n✓ 改造完成: {len(TOOL_PAGES)} 个工具页")


if __name__ == "__main__":
    main()
