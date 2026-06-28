"""
配置中心 - 从环境变量读取配置，支持生产/开发环境切换
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# ── 项目根目录 ──
BASE_DIR = Path(__file__).resolve().parent

# ── Flask 配置 ──
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    # 生产环境必须有 SECRET_KEY，否则拒绝启动
    if os.environ.get('FLASK_ENV') == 'production':
        raise ValueError("生产环境必须设置 SECRET_KEY 环境变量")
    # 开发环境使用随机 key
    SECRET_KEY = os.urandom(24).hex()

FLASK_ENV = os.environ.get('FLASK_ENV', 'production')
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# ── 站点配置 ──
SITE_URL = os.environ.get('SITE_URL', 'https://tools.292029.xyz').rstrip('/')
SITE_NAME = os.environ.get('SITE_NAME', '办公效率工具集')

# ── 文件上传配置 ──
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 500 * 1024 * 1024))  # 500MB
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'output'

# 确保目录存在
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 清理配置 ──
CLEANUP_INTERVAL = int(os.environ.get('CLEANUP_INTERVAL', 600))  # 10 分钟
FILE_EXPIRE_SECONDS = int(os.environ.get('FILE_EXPIRE_SECONDS', 1800))  # 30 分钟

# ── 限流配置 ──
RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '10 per minute')
RATE_LIMIT_UPLOAD = os.environ.get('RATE_LIMIT_UPLOAD', '5 per minute')

# ── OCR 配置 ──
OCR_MAX_FILE_BYTES = int(os.environ.get('OCR_MAX_FILE_BYTES', 50 * 1024 * 1024))  # 50MB
OCR_MAX_PAGES = int(os.environ.get('OCR_MAX_PAGES', 100))

# ── 允许的文件扩展名 ──
ALLOWED_EXT_XLS = {'.xls'}
ALLOWED_EXT_PDF = {'.pdf'}
ALLOWED_EXT_IMAGE = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
ALLOWED_EXT_OFFICE = {'.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx'}

# ── PDF 配置 ──
MAX_PDF_MERGE_FILES = 20
MAX_PDF_SIZE_BYTES = 200 * 1024 * 1024  # 单 PDF 200MB

# ── 图片转 PDF 配置 ──
MAX_IMAGES_TO_PDF = 10

# ── SEO 元数据配置 ──
SEO_META = {
    'index': {
        'title': '办公效率工具集 - 免费在线PDF/图片/编码转换工具',
        'description': '免费的在线办公工具集：PDF 转 Word/合并/拆分/压缩/加水印/加密、图片压缩/格式转换/转 PDF、XLS 转 XLSX/CSV 转换、Base64/JSON/时间戳编码转换。无需注册，保护隐私。',
        'keywords': '在线办公工具,PDF转换,图片处理,免费工具,在线工具,文件转换,编码转换,二维码生成',
        'path': '/',
    },
    'xls_to_xlsx': {
        'title': 'XLS 转 XLSX 在线转换工具 - 免费保留格式与图片',
        'description': '在线将 Excel 97-2003 (.xls) 转换为现代 .xlsx 格式，基于 LibreOffice 引擎，完整保留内容、格式、图片、图表。单文件最大 500MB，30 分钟自动清理。',
        'keywords': 'XLS转XLSX,Excel格式转换,xls,xlsx,Excel 97-2003,LibreOffice,在线转换,文件转换',
        'path': '/xls-to-xlsx',
    },
    'pdf_to_word': {
        'title': 'PDF 转 Word (DOCX) 在线工具 - 保留原始排版与 OCR',
        'description': '在线将 PDF 转换为可编辑 Word (DOCX) 文档，基于 pdf2docx 引擎，完整保留原始排版、表格、字体和图片。支持扫描件 OCR 识别，单文件最大 200MB。',
        'keywords': 'PDF转Word,PDF转DOCX,PDF转换,在线PDF转换,OCR,扫描件识别,文档转换,pdf2docx',
        'path': '/pdf-to-word',
    },
    'image_compress': {
        'title': '图片压缩在线工具 - JPG/PNG/WebP 智能压缩',
        'description': '在线压缩 JPG/PNG/WebP 图片，自定义质量和尺寸，智能保持视觉质量。支持批量上传，单文件最大 50MB，免费无需注册。',
        'keywords': '图片压缩,在线压缩,JPG压缩,PNG压缩,WebP压缩,图片优化,智能压缩,文件压缩',
        'path': '/image-compress',
    },
    'image_convert': {
        'title': '图片格式转换工具 - JPG/PNG/WebP/BMP/GIF/TIFF',
        'description': '在线图片格式转换，支持 JPG/PNG/WebP/BMP/GIF/TIFF 互转。保留原图质量，可设置输出尺寸，单文件最大 50MB。',
        'keywords': '图片格式转换,图片转换,JPG转PNG,PNG转JPG,WebP转换,在线转换,免费图片工具',
        'path': '/image-convert',
    },
    'images_to_pdf': {
        'title': '图片转 PDF 在线工具 - 多图合并 PDF',
        'description': '在线将多张图片（JPG/PNG/WebP）合并为一个 PDF 文件，每张图片一页。可调整顺序，支持 1-10 张图片，单文件最大 50MB。',
        'keywords': '图片转PDF,图片合并,在线PDF制作,JPG转PDF,PNG转PDF,多图合并,PDF生成',
        'path': '/images-to-pdf',
    },
    'hash_check': {
        'title': '文件哈希校验工具 - MD5/SHA1/SHA256/SHA512',
        'description': '在线计算文件 MD5/SHA1/SHA256/SHA512 哈希值，验证文件完整性和安全性。本地计算，文件不上传服务器，保护隐私。',
        'keywords': '哈希校验,文件校验,MD5,SHA1,SHA256,SHA512,文件完整性,本地计算,哈希值',
        'path': '/hash-check',
    },
    'base64': {
        'title': 'Base64 编解码在线工具 - 支持 UTF-8 中文',
        'description': '在线 Base64 编码解码工具，支持 UTF-8 中文字符。文本与 Base64 双向转换，结果可一键复制，完全本地处理无需上传。',
        'keywords': 'Base64编码,Base64解码,Base64在线,UTF-8编码,文本编码,本地处理,免费工具',
        'path': '/base64',
    },
    'json_tool': {
        'title': 'JSON 格式化工具 - 美化/压缩/校验/错误定位',
        'description': '在线 JSON 格式化、压缩、校验、错误定位。支持语法高亮，定位错误行列号，开发者必备工具。完全本地处理，文件不上传。',
        'keywords': 'JSON格式化,JSON美化,JSON压缩,JSON校验,JSON修复,开发者工具,在线JSON',
        'path': '/json-tool',
    },
    'timestamp': {
        'title': 'Unix 时间戳转换工具 - 秒/毫秒双向转换',
        'description': '在线 Unix 时间戳与日期时间互转，支持秒和毫秒自动识别。显示���京时间，可一键复制结果，开发者常用工具。',
        'keywords': '时间戳转换,Unix时间戳,时间戳,日期转换,毫秒转换,北京时区,在线工具',
        'path': '/timestamp',
    },
    'pdf_merge': {
        'title': 'PDF 合并在线工具 - 多文件合并保留书签',
        'description': '在线将多个 PDF 文件合并为一个，支持拖拽调整顺序，保留原始书签和元数据。最多 20 个文件，单文件最大 200MB。',
        'keywords': 'PDF合并,PDF拼接,合并PDF,在线PDF,文件合并,书签保留,多文件合并',
        'path': '/pdf-merge',
    },
    'pdf_split': {
        'title': 'PDF 拆分在线工具 - 按页码范围提取页面',
        'description': '在线从 PDF 中提取指定页面或页码范围，生成新的 PDF 文件。支持单页、多页、范围多种提取模式，保留原始质量。',
        'keywords': 'PDF拆分,PDF分割,PDF提取,按页码提取,PDF页面,在线工具,免费PDF',
        'path': '/pdf-split',
    },
    'pdf_compress': {
        'title': 'PDF 压缩在线工具 - 三档压缩节省空间',
        'description': '在线压缩 PDF 文件，通过图像降采样减小体积，三档压缩级别（轻度/中度/激进）。适合扫描件优化，最高可减少 80% 体积。',
        'keywords': 'PDF压缩,PDF优化,文件压缩,扫描件优化,在线PDF,免费PDF工具,PDF减肥',
        'path': '/pdf-compress',
    },
    'qrcode': {
        'title': '二维码生成工具 - 文本/网址/WiFi/邮箱/电话',
        'description': '在线生成文本、网址、WiFi、邮箱、电话等多种类型二维码。支持 PNG 和 SVG 矢量下载，可自定义颜色和尺寸，免费使用。',
        'keywords': '二维码生成,QR Code,WiFi二维码,网址二维码,SVG二维码,在线工具,免费',
        'path': '/qrcode',
    },
    'pdf_watermark': {
        'title': 'PDF 加水印在线工具 - 平铺文字水印',
        'description': '在线为 PDF 添加平铺文字水印，支持自定义字体、大小、颜色、透明度、旋转角度。保护文档版权，输出文件保留原样可阅读。',
        'keywords': 'PDF水印,加水印,PDF版权,文字水印,平铺水印,PDF保护,在线PDF工具',
        'path': '/pdf-watermark',
    },
    'pdf_encrypt': {
        'title': 'PDF 加密/解密在线工具 - AES 256 强加密',
        'description': '在线为 PDF 设置密码保护或移除已知密码。AES 256 位强加密，可分别设置用户密码（打开）和所有者密码（编辑权限）。',
        'keywords': 'PDF加密,PDF解密,PDF密码,AES加密,文档保护,PDF安全,在线加密',
        'path': '/pdf-encrypt',
    },
    'csv_excel': {
        'title': 'CSV 与 Excel 互转工具 - 智能识别编码解决乱码',
        'description': '在线 CSV 与 Excel (XLSX) 互相转换，自动识别编码（UTF-8/GBK/GB2312），彻底解决中文乱码问题。可自定义分隔符。',
        'keywords': 'CSV转Excel,Excel转CSV,CSV转换,编码识别,中文乱码,UTF-8,GBK,在线转换',
        'path': '/csv-excel',
    },
    'zh_convert': {
        'title': 'Office 文档简繁转换工具 - Word/Excel/PPT 在线互转',
        'description': '在线将 Word (.doc/.docx)、Excel (.xls/.xlsx)、PowerPoint (.ppt/.pptx) 文档进行简体与繁体中文互转，基于 OpenCC 引擎，完整保留原排版、字体、表格、图表。支持 6 种 Office 格式。',
        'keywords': '简繁转换,繁体转换,简体转繁体,繁体转简体,Word简繁,Excel简繁,PPT简繁,OpenCC,在线转换,文档转换',
        'path': '/zh-convert',
    },
}

# ── 简繁转换配置 ──
ZH_OLD_TO_NEW_EXT = {'.doc': '.docx', '.xls': '.xlsx', '.ppt': '.pptx'}
ZH_DIRECTION_SUFFIX = {'s2t': '_s2t', 't2s': '_t2s'}
ZH_VALID_DIRECTIONS = {'s2t', 't2s'}

# ── PDF 压缩档位配置 ──
PDF_COMPRESS_LEVELS = {
    'screen':  (1240, 1754, 75),   # 150 DPI 屏幕浏览
    'email':   (827,  1169, 60),   # 100 DPI 邮件附件
    'extreme': (595,  842,  50),   # 72 DPI 极限压缩
}

# ── 二维码纠错级别映射 ──
QR_EC_MAP = {'L': 1, 'M': 0, 'Q': 3, 'H': 2}

# ── 日志配置 ──
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'