#!/usr/bin/env python3
"""
office-tools — 办公效率工具集 Web 应用

重构版：使用配置中心、统一日志、速率限制、CSRF 保护
"""
import os
import io
import uuid
import time
import shutil
import subprocess
import threading
import concurrent.futures
from pathlib import Path

# ── 导入配置 ─────────────────────────────────────────────────────
from config import (
    SECRET_KEY, FLASK_ENV, SITE_URL, SITE_NAME, MAX_CONTENT_LENGTH,
    UPLOAD_DIR, OUTPUT_DIR, SEO_META,
    ALLOWED_EXT_XLS, ALLOWED_EXT_PDF, ALLOWED_EXT_IMAGE, ALLOWED_EXT_OFFICE,
    MAX_PDF_MERGE_FILES, MAX_PDF_SIZE_BYTES, MAX_IMAGES_TO_PDF,
    ZH_OLD_TO_NEW_EXT, ZH_DIRECTION_SUFFIX, ZH_VALID_DIRECTIONS,
    PDF_COMPRESS_LEVELS, QR_EC_MAP,
    OCR_MAX_FILE_BYTES, OCR_MAX_PAGES,
)

# ── 导入工具模块 ─────────────���───────────────────────────────────
from utils.logging_config import get_logger, setup_logging
from utils.cleanup import cleanup_startup, cleanup_scheduled
from utils.rate_limit import init_limiter, RATE_LIMITS
from utils.download import make_download_response, make_json_response
from utils.cleanup import cleanup_file as _cleanup_file

# ── 初始化日志 ───────────────────────────────────────────────────
logger = get_logger(__name__)

# ── 初始化 Flask 应用 ─────────────────────────────────────────────
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

# 加载配置
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Jinja2 配置：让 {%- ... -%} 块能干净地输出
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# ── 初始化限流器 ─────────────────────────────────────────────────
limiter = init_limiter(app)

# ── CSRF 保护 (仅在生产环境启用) ─────────────────────────────────
if FLASK_ENV == 'production':
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    logger.info("CSRF 保护已启用")
else:
    # 开发环境禁用 CSRF 方便测试
    app.config['WTF_CSRF_ENABLED'] = False
    logger.warning("CSRF 保护已禁用（开发模式）")

# ── SEO 元数据注入 ───────────────────────────────────────────────
@app.context_processor
def inject_seo():
    """向所有模板注入 site_url / site_name / seo_meta / 工具列表。"""
    return {
        'site_url': SITE_URL,
        'site_name': SITE_NAME,
        'seo_meta': SEO_META,
    }

# ── 目录初始化 ───────────────────────────────────────────────────
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 后台定时清理 ─────────────────────────────────────────────────
_CLEANUP_INTERVAL = 600  # 每10分钟
_last_cleanup = time.time()
_cleanup_lock = threading.Lock()


def _periodic_cleanup():
    """定时清理过期文件"""
    cleanup_scheduled()


# ── 健康检查端点 ─────────────────────────────────────────────────
_start_time = time.time()


@app.route('/health')
def health():
    """健康检查端点"""
    uptime = time.time() - _start_time
    return jsonify(
        status='ok',
        uptime_seconds=round(uptime, 2),
        version='1.0.0',
    )


@app.route('/readiness')
def readiness():
    """就绪检查：检查关键组件是否可用"""
    checks = {
        'upload_dir': UPLOAD_DIR.exists() and os.access(UPLOAD_DIR, os.W_OK),
        'output_dir': OUTPUT_DIR.exists() and os.access(OUTPUT_DIR, os.W_OK),
    }
    
    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503
    
    return jsonify(
        status='ready' if all_ok else 'not_ready',
        checks=checks,
    ), status_code


# ── 启动时清理 ───────────────────────────────────────────────────
_initialized = False

@app.before_request
def before_request():
    """首次请求时执行初始化"""
    global _initialized
    if not _initialized:
        _initialized = True
        logger.info("应用首次启动，执行初始化...")
        cleanup_startup()


# ── 全局请求后清理钩子 ───────────────────────────────────────────
@app.after_request
def cleanup_after_request(response):
    """全局：定时清理过期文件"""
    _periodic_cleanup()
    return response


# ═══════════════════════════════════════════════════════════════════
# 以下是从原 app.py 迁移的转换函数（保持功能不变，仅添加日志）
# ═══════════════════════════════════════════════════════════════════

# ── 转换函数 ──────────────────────────────────────────────────────

def convert_xls_to_xlsx(src_path: Path, dst_path: Path) -> dict:
    """通过 LibreOffice 将 .xls 转换为 .xlsx"""
    os.chmod(src_path, 0o644)
    try:
        work_dir = dst_path.parent.resolve()
        result = subprocess.run(
            [
                'libreoffice',
                '--headless',
                '--norestore',
                '--nofirststartwizard',
                '--convert-to', 'xlsx:Calc MS Excel 2007 XML',
                '--outdir', str(work_dir),
                str(src_path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        src_stem = src_path.stem
        generated = work_dir / f'{src_stem}.xlsx'

        if not generated.exists():
            candidates = list(work_dir.glob('*.xlsx'))
            generated = candidates[0] if candidates else None

        if generated and generated.exists():
            if generated.resolve() != dst_path.resolve():
                shutil.move(str(generated), str(dst_path))
            logger.info(f"XLS 转 XLSX 成功: {src_path.name} -> {dst_path.name}")
            return {"success": True, "error": None}

        logger.error(f"LibreOffice 未生成目标文件: {result.stderr}")
        return {
            "success": False,
            "error": f"LibreOffice 未生成目标文件。stderr: {result.stderr}",
        }

    except subprocess.TimeoutExpired:
        logger.error("XLS 转 XLSX 超时（>300s）")
        return {"success": False, "error": "转换超时（>300s）"}
    except FileNotFoundError:
        logger.error("系统中未找到 libreoffice 命令")
        return {"success": False, "error": "系统中未找到 libreoffice 命令，请安装 LibreOffice"}
    except Exception as e:
        logger.error(f"XLS 转 XLSX 失败: {e}")
        return {"success": False, "error": str(e)}


def convert_pdf_to_docx(src_path: Path, dst_path: Path) -> dict:
    """通过 pdf2docx 将 PDF 转换为 DOCX"""
    try:
        from pdf2docx import Converter

        cv = Converter(str(src_path))
        cv.convert(str(dst_path), start=0, end=None)
        cv.close()

        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 转 DOCX 成功: {src_path.name}")
            return {"success": True, "error": None}
        logger.error("PDF 转 DOCX 后文件为空")
        return {"success": False, "error": "转换后文件为空"}

    except ImportError:
        logger.error("缺少 pdf2docx 库")
        return {"success": False, "error": "缺少 pdf2docx 库，请执行: pip install pdf2docx"}
    except Exception as e:
        logger.error(f"PDF 转 DOCX 失败: {e}")
        return {"success": False, "error": f"转换失败: {e}"}


# ── PDF 合并/拆分/压缩 ───────────────────────────────────────────

def _parse_page_ranges(spec: str, total: int) -> list:
    """解析页码范围语法"""
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


def merge_pdfs(src_paths: list, dst_path: Path) -> dict:
    """合并多个 PDF 文件"""
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for src in src_paths:
            writer.append(str(src))

        with open(dst_path, 'wb') as f:
            writer.write(f)
        writer.close()

        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 合并成功: {len(src_paths)} 个文件 -> {dst_path.name}")
            return {"success": True, "error": None}
        return {"success": False, "error": "合并后文件为空"}

    except ImportError:
        return {"success": False, "error": "缺少 pypdf 库，请执行: pip install pypdf"}
    except Exception as e:
        logger.error(f"PDF 合并失败: {e}")
        return {"success": False, "error": f"合并失败: {e}"}


def split_pdf(src_path: Path, dst_path: Path, page_spec: str) -> dict:
    """从 PDF 中按页码范围提取页面"""
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(str(src_path))
        total = len(reader.pages)

        try:
            selected = _parse_page_ranges(page_spec, total)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if len(selected) == total:
            shutil.copy(str(src_path), str(dst_path))
        else:
            writer = PdfWriter()
            for p in selected:
                writer.add_page(reader.pages[p - 1])
            with open(dst_path, 'wb') as f:
                writer.write(f)
            writer.close()

        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 拆分成功: {src_path.name} 提取页 {page_spec}")
            return {"success": True, "error": None,
                    "selected_pages": selected, "total_pages": total}
        return {"success": False, "error": "拆分后文件为空"}

    except ImportError:
        return {"success": False, "error": "缺少 pypdf 库，请执行: pip install pypdf"}
    except Exception as e:
        logger.error(f"PDF 拆分失败: {e}")
        return {"success": False, "error": f"拆分失败: {e}"}


def add_pdf_watermark(src_path: Path, dst_path: Path, text: str, 
                      font_size: int = 40, opacity: float = 0.3, 
                      rotation: int = 45) -> dict:
    """为 PDF 每页添加平铺文字水印"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from pypdf import PdfReader, PdfWriter
        
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        
        reader = PdfReader(str(src_path))
        writer = PdfWriter()
        
        for page in reader.pages:
            media_box = page.mediabox
            page_width = float(media_box.width)
            page_height = float(media_box.height)
            
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(page_width, page_height))
            
            c.saveState()
            c.setFillColorRGB(0.5, 0.5, 0.5, opacity)
            c.setFont('STSong-Light', font_size)
            
            text_width = c.stringWidth(text, 'STSong-Light', font_size)
            spacing_x = text_width + 150
            spacing_y = font_size + 200
            
            y = -font_size
            while y < page_height + font_size:
                x = -text_width
                while x < page_width + text_width:
                    c.saveState()
                    c.translate(x, y)
                    c.rotate(rotation)
                    c.drawString(0, 0, text)
                    c.restoreState()
                    x += spacing_x
                y += spacing_y
            
            c.restoreState()
            c.save()
            
            packet.seek(0)
            watermark_pdf = PdfReader(packet)
            watermark_page = watermark_pdf.pages[0]
            page.merge_page(watermark_page)
            writer.add_page(page)
        
        with open(dst_path, 'wb') as f:
            writer.write(f)
        
        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 加水印成功: {src_path.name}")
            return {"success": True, "error": None}
        return {"success": False, "error": "水印添加后文件为空"}
        
    except ImportError:
        return {"success": False, "error": "缺少依赖库，请执行: pip install reportlab pypdf"}
    except Exception as e:
        logger.error(f"PDF 加水印失败: {e}")
        return {"success": False, "error": f"添加水印失败: {e}"}


def encrypt_pdf(src_path: Path, dst_path: Path, password: str, 
                owner_password: str = None) -> dict:
    """为 PDF 添加密码保护"""
    try:
        from pypdf import PdfReader, PdfWriter
        
        reader = PdfReader(str(src_path))
        writer = PdfWriter()
        
        for page in reader.pages:
            writer.add_page(page)
        
        if owner_password:
            writer.encrypt(user_password=password, owner_password=owner_password)
        else:
            writer.encrypt(user_password=password)
        
        with open(dst_path, 'wb') as f:
            writer.write(f)
        
        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 加密成功: {src_path.name}")
            return {"success": True, "error": None}
        return {"success": False, "error": "加密后文件为空"}
        
    except ImportError:
        return {"success": False, "error": "缺少 pypdf 库，请执行: pip install pypdf"}
    except Exception as e:
        logger.error(f"PDF 加密失败: {e}")
        return {"success": False, "error": f"加密失败: {e}"}


def decrypt_pdf(src_path: Path, dst_path: Path, password: str) -> dict:
    """解密已加密的 PDF"""
    try:
        from pypdf import PdfReader, PdfWriter
        
        reader = PdfReader(str(src_path))
        
        if not reader.is_encrypted:
            return {"success": False, "error": "该 PDF 未被加密"}
        
        try:
            status = reader.decrypt(password)
            if status == 0:
                return {"success": False, "error": "密码错误，无法解密"}
        except Exception:
            return {"success": False, "error": "密码错误，无法解密"}
        
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        
        with open(dst_path, 'wb') as f:
            writer.write(f)
        
        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 解密成功: {src_path.name}")
            return {"success": True, "error": None}
        return {"success": False, "error": "解密后文件为空"}
        
    except ImportError:
        return {"success": False, "error": "缺少 pypdf 库，请执行: pip install pypdf"}
    except Exception as e:
        logger.error(f"PDF 解密失败: {e}")
        return {"success": False, "error": f"解密失败: {e}"}


# ── CSV ↔ Excel ──────────────────────────────────────────────────

def convert_csv_to_excel(src_path: Path, dst_path: Path, 
                         encoding: str = 'utf-8', delimiter: str = ',') -> dict:
    """将 CSV 转换为 Excel (.xlsx)"""
    try:
        import pandas as pd
        
        df = None
        if encoding == 'auto':
            for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'big5', 'latin-1']:
                try:
                    df = pd.read_csv(str(src_path), encoding=enc, delimiter=delimiter)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
        else:
            try:
                df = pd.read_csv(str(src_path), encoding=encoding, delimiter=delimiter)
            except (UnicodeDecodeError, UnicodeError):
                for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
                    try:
                        df = pd.read_csv(str(src_path), encoding=enc, delimiter=delimiter)
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
        
        if df is None:
            return {"success": False, "error": "无法识别文件编码，请手动指定"}
        
        df.to_excel(str(dst_path), index=False, engine='openpyxl')
        
        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"CSV 转 Excel 成功: {src_path.name}")
            return {"success": True, "error": None, 
                    "rows": len(df), "columns": len(df.columns)}
        return {"success": False, "error": "转换后文件为空"}
        
    except ImportError:
        return {"success": False, "error": "缺少依赖库，请执行: pip install pandas openpyxl"}
    except Exception as e:
        logger.error(f"CSV 转 Excel 失败: {e}")
        return {"success": False, "error": f"转换失败: {e}"}


def convert_excel_to_csv(src_path: Path, dst_path: Path, 
                         encoding: str = 'utf-8', delimiter: str = ',',
                         sheet_name: str = None) -> dict:
    """将 Excel (.xlsx/.xls) 转换为 CSV"""
    try:
        import pandas as pd
        
        if sheet_name:
            df = pd.read_excel(str(src_path), sheet_name=sheet_name, engine='openpyxl')
        else:
            df = pd.read_excel(str(src_path), sheet_name=0, engine='openpyxl')
        
        df.to_csv(str(dst_path), index=False, encoding=encoding, sep=delimiter)
        
        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"Excel 转 CSV 成功: {src_path.name}")
            return {"success": True, "error": None,
                    "rows": len(df), "columns": len(df.columns)}
        return {"success": False, "error": "转换后文件为空"}
        
    except ImportError:
        return {"success": False, "error": "缺少依赖库，请执行: pip install pandas openpyxl"}
    except Exception as e:
        logger.error(f"Excel 转 CSV 失败: {e}")
        return {"success": False, "error": f"转换失败: {e}"}


def generate_qrcode(payload: str, error_level: str = 'M',
                    fg_color: str = '#000000', bg_color: str = '#ffffff',
                    box_size: int = 10, border: int = 2) -> dict:
    """生成二维码，返回 PNG (bytes) + SVG (str) + 元数据"""
    try:
        import qrcode
        from qrcode.constants import (
            ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H,
        )
        from qrcode.image.svg import SvgPathImage

        ec_map = {
            'L': ERROR_CORRECT_L, 'M': ERROR_CORRECT_M,
            'Q': ERROR_CORRECT_Q, 'H': ERROR_CORRECT_H,
        }
        ec = ec_map.get(error_level.upper(), ERROR_CORRECT_M)

        if not payload:
            return {"success": False, "error": "内容不能为空"}

        if len(payload) > 2000:
            return {"success": False, "error": "内容过长（最大 2000 字符）"}

        qr = qrcode.QRCode(
            version=None,
            error_correction=ec,
            box_size=box_size,
            border=border,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        modules = qr.modules_count

        # 生成 PNG
        img = qr.make_image(fill_color=fg_color, back_color=bg_color)
        png_buf = io.BytesIO()
        img.save(png_buf, 'PNG')
        png_bytes = png_buf.getvalue()

        # 生成 SVG
        svg_factory = SvgPathImage
        img_svg = qr.make_image(image_factory=svg_factory,
                                fill_color=fg_color, back_color=bg_color)
        svg_buf = io.BytesIO()
        img_svg.save(svg_buf)
        svg_str = svg_buf.getvalue().decode('utf-8')

        logger.debug(f"二维码生成成功: {len(payload)} 字符")
        return {
            "success": True,
            "error": None,
            "png": png_bytes,
            "svg": svg_str,
            "modules": modules,
            "bytes_len": len(payload.encode('utf-8')),
            "char_len": len(payload),
        }

    except ImportError:
        return {"success": False, "error": "缺少 qrcode 库，请执行: pip install qrcode"}
    except Exception as e:
        logger.error(f"二维码生成失败: {e}")
        return {"success": False, "error": f"生成失败: {e}"}


def compress_pdf(src_path: Path, dst_path: Path, level: str = 'screen') -> dict:
    """PDF 压缩：图像降采样 + JPEG 重压缩 + stream 压缩"""
    try:
        import pikepdf
        from pikepdf import Pdf, PdfImage, Name
        from PIL import Image

        if level not in PDF_COMPRESS_LEVELS:
            return {"success": False,
                    "error": f'无效压缩级别 "{level}"，可选: {", ".join(PDF_COMPRESS_LEVELS.keys())}'}

        max_w, max_h, jpeg_q = PDF_COMPRESS_LEVELS[level]
        n_images_processed = 0

        with Pdf.open(str(src_path)) as pdf:
            for page in pdf.pages:
                for name, obj in list(page.images.items()):
                    try:
                        pim = PdfImage(obj)
                        if pim.image_mask:
                            continue
                        if pim.width <= max_w and pim.height <= max_h:
                            continue
                        pil = pim.as_pil_image()
                        pil.thumbnail((max_w, max_h), Image.LANCZOS)
                        if pil.mode == 'CMYK':
                            pil = pil.convert('RGB')
                        buf = io.BytesIO()
                        pil.save(buf, 'JPEG', quality=jpeg_q)
                        obj.write(buf.getvalue(), filter=Name.DCTDecode)
                        obj.Width = pil.size[0]
                        obj.Height = pil.size[1]
                        n_images_processed += 1
                    except Exception:
                        continue

            pdf.save(str(dst_path), compress_streams=True,
                     object_stream_mode=pikepdf.ObjectStreamMode.generate)

        if dst_path.exists() and dst_path.stat().st_size > 0:
            logger.info(f"PDF 压缩成功: {src_path.name}, 级别: {level}, 处理 {n_images_processed} 张图片")
            return {"success": True, "error": None,
                    "level": level, "images_processed": n_images_processed}
        return {"success": False, "error": "压缩后文件为空"}

    except ImportError:
        return {"success": False,
                "error": "缺少 pikepdf 库，请执行: pip install pikepdf"}
    except Exception as e:
        logger.error(f"PDF 压缩失败: {e}")
        return {"success": False, "error": f"压缩失败: {e}"}


# ═══════════════════════════════════════════════════════════════════
# 图片处理辅助函数
# ═══════════════════════════════════════════════════════════════════

from PIL import Image as _PIL_Image


def _image_mime(ext: str) -> str:
    "图片扩展名 → MIME 类型"
    _map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.webp': 'image/webp',
        '.bmp': 'image/bmp', '.gif': 'image/gif',
        '.tiff': 'image/tiff',
    }
    return _map.get(ext, 'application/octet-stream')


def _pil_save_image(img, dst_path: Path, ext: str, quality: int = 85):
    """根据扩展名智能保存图片"""
    kwargs = {}
    if ext in ('.jpg', '.jpeg'):
        kwargs.update(quality=quality, optimize=True, subsampling=-1)
    elif ext == '.webp':
        kwargs['quality'] = quality
    elif ext == '.png':
        kwargs['optimize'] = True
    img.save(str(dst_path), **kwargs)


def _pil_prepare_for_jpeg(img, bg_color='white'):
    """将 RGBA/P/LA 模式转 RGB"""
    if img.mode in ('RGBA', 'P', 'LA'):
        bg = _PIL_Image.new('RGB', img.size, bg_color)
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode == 'RGBA':
            bg.paste(img, mask=img.split()[-1])
        elif img.mode == 'LA':
            bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode not in ('RGB', 'L'):
        return img.convert('RGB')
    return img


# ── 通用下载响应 ──────────────────────────────────────────────

def _make_download_response(dst_path, src_filename, new_ext, mime_type, src_path):
    """构造下载响应，下载完成后自动清理临时文件"""
    if not dst_path.exists():
        return jsonify(success=False, error='转换后未找到输出文件'), 500

    resp = send_file(
        str(dst_path),
        as_attachment=True,
        download_name=Path(src_filename).stem + new_ext,
        mimetype=mime_type,
    )

    original_src = src_path
    original_dst = dst_path

    @resp.call_on_close
    def _cleanup_on_close():
        _cleanup_file(original_src)
        _cleanup_file(original_dst)

    return resp


# ── 工具通用路由 ──────────────────────────────────────────────

def _handle_convert(ext_set, convert_fn, new_ext, mime_type):
    """通用文件转换处理"""
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ext_set:
        allowed = ', '.join(ext_set)
        return jsonify(success=False, error=f'不支持的文件类型 "{ext}"，仅支持 {allowed}'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}{ext}'
    dst_path = OUTPUT_DIR / f'{uid}{new_ext}'

    file.save(str(src_path))

    try:
        result = convert_fn(src_path, dst_path)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 500
        return _make_download_response(dst_path, file.filename, new_ext, mime_type, src_path)
    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"_handle_convert 处理失败: {e}")
        return jsonify(success=False, error=str(e)), 500


# ═══════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/xls-to-xlsx')
def xls_to_xlsx_page():
    return render_template('xls_to_xlsx.html')


@app.route('/pdf-to-word')
def pdf_to_word_page():
    return render_template('pdf_to_word.html')


@app.route('/image-compress')
def image_compress_page():
    return render_template('image_compress.html')


@app.route('/image-convert')
def image_convert_page():
    return render_template('image_convert.html')


@app.route('/images-to-pdf')
def images_to_pdf_page():
    return render_template('images_to_pdf.html')


@app.route('/hash-check')
def hash_check_page():
    return render_template('hash_check.html')


@app.route('/base64')
def base64_page():
    return render_template('base64.html')


@app.route('/json-tool')
def json_tool_page():
    return render_template('json_tool.html')


@app.route('/timestamp')
def timestamp_page():
    return render_template('timestamp.html')


@app.route('/pdf-merge')
def pdf_merge_page():
    return render_template('pdf_merge.html')


@app.route('/pdf-split')
def pdf_split_page():
    return render_template('pdf_split.html')


@app.route('/pdf-compress')
def pdf_compress_page():
    return render_template('pdf_compress.html')


@app.route('/qrcode')
def qrcode_page():
    return render_template('qrcode.html')


@app.route('/pdf-watermark')
def pdf_watermark_page():
    return render_template('pdf_watermark.html')


@app.route('/pdf-encrypt')
def pdf_encrypt_page():
    return render_template('pdf_encrypt.html')


@app.route('/csv-excel')
def csv_excel_page():
    return render_template('csv_excel.html')


@app.route('/zh-convert')
def zh_convert_page():
    return render_template('zh_convert.html')


# ═══════════════════════════════════════════════════════════════════
# SEO 基础设施：sitemap.xml + robots.txt
# ═══════════════════════════════════════════════════════════════════

@app.route('/sitemap.xml')
def sitemap_xml():
    """动态生成 sitemap.xml"""
    from flask import Response
    lastmod = time.strftime('%Y-%m-%d', time.gmtime())
    urls = []
    for slug, meta in SEO_META.items():
        urls.append({
            'loc': SITE_URL + meta['path'],
            'lastmod': lastmod,
            'changefreq': 'weekly' if slug == 'index' else 'monthly',
            'priority': '1.0' if slug == 'index' else '0.8',
        })
    body = ['<?xml version="1.0" encoding="UTF-8"?>']
    body.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        body.append('  <url>')
        body.append(f'    <loc>{u["loc"]}</loc>')
        body.append(f'    <lastmod>{u["lastmod"]}</lastmod>')
        body.append(f'    <changefreq>{u["changefreq"]}</changefreq>')
        body.append(f'    <priority>{u["priority"]}</priority>')
        body.append('  </url>')
    body.append('</urlset>')
    return Response('\n'.join(body), mimetype='application/xml; charset=utf-8')


@app.route('/robots.txt')
def robots_txt():
    """动态生成 robots.txt"""
    from flask import Response
    body = (
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /api/\n'
        'Disallow: /uploads/\n'
        'Disallow: /output/\n'
        '\n'
        f'Sitemap: {SITE_URL}/sitemap.xml\n'
    )
    return Response(body, mimetype='text/plain; charset=utf-8')


# ═══════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/convert/xls-to-xlsx', methods=['POST'])
def api_xls_to_xlsx():
    return _handle_convert(ALLOWED_EXT_XLS, convert_xls_to_xlsx, '.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/api/convert/pdf-to-docx', methods=['POST'])
def api_pdf_to_docx():
    return _handle_convert(ALLOWED_EXT_PDF, convert_pdf_to_docx, '.docx',
                           'application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# ── API：PDF 合并 ────────────────────────────────

@app.route('/api/convert/pdf-merge', methods=['POST'])
def api_pdf_merge():
    files = request.files.getlist('files')
    valid_files = [f for f in files if f and f.filename]

    if not valid_files:
        return jsonify(success=False, error='未上传文件'), 400
    if len(valid_files) < 2:
        return jsonify(success=False, error='至少需要 2 个 PDF 文件'), 400
    if len(valid_files) > MAX_PDF_MERGE_FILES:
        return jsonify(success=False,
                       error=f'最多支持 {MAX_PDF_MERGE_FILES} 个文件'), 400

    uid = uuid.uuid4().hex
    src_paths = []
    try:
        for i, f in enumerate(valid_files):
            ext = Path(f.filename).suffix.lower()
            if ext != '.pdf':
                for sp in src_paths:
                    _cleanup_file(sp)
                return jsonify(success=False,
                               error=f'文件 "{f.filename}" 不是 PDF 格式'), 400
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(0)
            if size > MAX_PDF_SIZE_BYTES:
                for sp in src_paths:
                    _cleanup_file(sp)
                return jsonify(success=False,
                               error=f'文件 "{f.filename}" 超过 {MAX_PDF_SIZE_BYTES // 1024 // 1024}MB 限制'), 400

            sp = UPLOAD_DIR / f'{uid}_{i}{ext}'
            f.save(str(sp))
            src_paths.append(sp)

        dst_path = OUTPUT_DIR / f'{uid}.pdf'
        result = merge_pdfs(src_paths, dst_path)
        if not result['success']:
            return jsonify(success=False, error=result['error']), 500

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=f'merged_{uid[:8]}.pdf',
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src_paths_=src_paths, dst_path_=dst_path):
            for sp in src_paths_:
                _cleanup_file(sp)
            _cleanup_file(dst_path_)

        return resp

    except Exception as e:
        for sp in src_paths:
            _cleanup_file(sp)
        _cleanup_file(OUTPUT_DIR / f'{uid}.pdf')
        logger.error(f"PDF 合并失败: {e}")
        return jsonify(success=False, error=f'合并失败: {e}'), 500


# ── API：PDF 拆分 ────────────────────────────────

@app.route('/api/convert/pdf-split', methods=['POST'])
def api_pdf_split():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    page_spec = request.form.get('pages', '').strip()
    if not page_spec:
        return jsonify(success=False, error='请输入要提取的页码范围'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    file.save(str(src_path))

    try:
        result = split_pdf(src_path, dst_path, page_spec)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 400

        safe_pages = page_spec.replace(',', '_').replace(' ', '')
        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}_pages_{safe_pages}.pdf'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"PDF 拆分失败: {e}")
        return jsonify(success=False, error=f'拆分失败: {e}'), 500


# ── API：PDF 压缩 ────────────────────────────────

@app.route('/api/convert/pdf-compress', methods=['POST'])
def api_pdf_compress():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    level = request.form.get('level', 'screen').strip().lower()
    if level not in PDF_COMPRESS_LEVELS:
        return jsonify(success=False,
                       error=f'无效压缩级别 "{level}"，可选: {", ".join(PDF_COMPRESS_LEVELS.keys())}'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    file.save(str(src_path))

    try:
        orig_size = src_path.stat().st_size
        result = compress_pdf(src_path, dst_path, level)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 500

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}_compressed_{level}.pdf'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"PDF 压缩失败: {e}")
        return jsonify(success=False, error=f'压缩失败: {e}'), 500


# ── API：PDF 水印 ────────────────────────────────

@app.route('/api/convert/pdf-watermark', methods=['POST'])
def api_pdf_watermark():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    text = request.form.get('text', '').strip()
    if not text:
        return jsonify(success=False, error='请输入水印文字'), 400
    if len(text) > 100:
        return jsonify(success=False, error='水印文字过长（最多 100 字符）'), 400

    font_size = max(10, min(200, request.form.get('font_size', 40, type=int)))
    opacity = max(0.05, min(1.0, request.form.get('opacity', 0.3, type=float)))
    rotation = max(-90, min(90, request.form.get('rotation', 45, type=int)))

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    file.save(str(src_path))

    try:
        result = add_pdf_watermark(src_path, dst_path, text, font_size, opacity, rotation)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 500

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}_watermarked.pdf'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"PDF 加水印失败: {e}")
        return jsonify(success=False, error=f'添加水印失败: {e}'), 500


# ── API：PDF 加密 ────────────────────────────────

@app.route('/api/convert/pdf-encrypt', methods=['POST'])
def api_pdf_encrypt():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    password = request.form.get('password', '').strip()
    if not password:
        return jsonify(success=False, error='请输入密码'), 400
    if len(password) > 128:
        return jsonify(success=False, error='密码过长（最多 128 字符）'), 400

    owner_password = request.form.get('owner_password', '').strip()
    if owner_password and len(owner_password) > 128:
        return jsonify(success=False, error='所有者密码过长（最多 128 字符）'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    file.save(str(src_path))

    try:
        result = encrypt_pdf(src_path, dst_path, password, owner_password if owner_password else None)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 500

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}_encrypted.pdf'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"PDF 加密失败: {e}")
        return jsonify(success=False, error=f'加密失败: {e}'), 500
# ── API：PDF 解密 ────────────────────────────────

@app.route('/api/convert/pdf-decrypt', methods=['POST'])
def api_pdf_decrypt():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    password = request.form.get('password', '').strip()
    if not password:
        return jsonify(success=False, error='请输入密码'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    file.save(str(src_path))

    try:
        result = decrypt_pdf(src_path, dst_path, password)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 400

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}_decrypted.pdf'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"PDF 解密失败: {e}")
        return jsonify(success=False, error=f'解密失败: {e}'), 500


# ── API：CSV → Excel ────────────────────────────────

@app.route('/api/convert/csv-to-excel', methods=['POST'])
def api_csv_to_excel():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.csv':
        return jsonify(success=False, error='仅支持 .csv 格式'), 400

    encoding = request.form.get('encoding', 'utf-8').strip()
    delimiter = request.form.get('delimiter', ',').strip()

    if len(delimiter) != 1:
        return jsonify(success=False, error='分隔符必须是单个字符'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.csv'
    dst_path = OUTPUT_DIR / f'{uid}.xlsx'
    file.save(str(src_path))

    try:
        result = convert_csv_to_excel(src_path, dst_path, encoding, delimiter)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 400

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}.xlsx'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"CSV 转 Excel 失败: {e}")
        return jsonify(success=False, error=f'转换失败: {e}'), 500


# ── API：Excel → CSV ────────────────────────────────

@app.route('/api/convert/excel-to-csv', methods=['POST'])
def api_excel_to_csv():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in {'.xlsx', '.xls'}:
        return jsonify(success=False, error='仅支持 .xlsx 或 .xls 格式'), 400

    encoding = request.form.get('encoding', 'utf-8').strip()
    delimiter = request.form.get('delimiter', ',').strip()
    sheet_name = request.form.get('sheet_name', '').strip() or None

    if len(delimiter) != 1:
        return jsonify(success=False, error='分隔符必须是单个字符'), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}{ext}'
    dst_path = OUTPUT_DIR / f'{uid}.csv'
    file.save(str(src_path))

    try:
        result = convert_excel_to_csv(src_path, dst_path, encoding, delimiter, sheet_name)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 400

        original_stem = Path(file.filename).stem
        download_name = f'{original_stem}.csv'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype='text/csv',
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"Excel 转 CSV 失败: {e}")
        return jsonify(success=False, error=f'转换失败: {e}'), 500


# ── API：二维码生成 ─────────────────────────────

@app.route('/api/qrcode', methods=['POST'])
def api_qrcode():
    data = request.get_json(silent=True) or {}
    payload = data.get('payload', '').strip()
    error_level = data.get('error_level', 'M').strip().upper()
    fg_color = data.get('fg_color', '#000000').strip()
    bg_color = data.get('bg_color', '#ffffff').strip()
    box_size = int(data.get('box_size', 10))
    border = int(data.get('border', 2))

    if error_level not in QR_EC_MAP:
        return jsonify(success=False,
                       error=f'无效纠错级别 "{error_level}"'), 400

    if not fg_color.startswith('#') or len(fg_color) not in (4, 7):
        return jsonify(success=False, error='前景色格式错误（需 #RGB 或 #RRGGBB）'), 400
    if not bg_color.startswith('#') or len(bg_color) not in (4, 7):
        return jsonify(success=False, error='背景色格式错误（需 #RGB 或 #RRGGBB）'), 400

    box_size = max(1, min(50, box_size))
    border = max(0, min(10, border))

    result = generate_qrcode(
        payload, error_level, fg_color, bg_color, box_size, border,
    )
    if not result['success']:
        return jsonify(success=False, error=result['error']), 400

    import base64 as _b64
    return jsonify(
        success=True,
        png_base64=_b64.b64encode(result['png']).decode('ascii'),
        svg=result['svg'],
        modules=result['modules'],
        bytes_len=result['bytes_len'],
        char_len=result['char_len'],
    )


# ── API：图片压缩 ────────────────────────────────────────

@app.route('/api/convert/image-compress', methods=['POST'])
def api_image_compress():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT_IMAGE:
        allowed = ', '.join(ALLOWED_EXT_IMAGE)
        return jsonify(success=False, error=f'不支持的文件类型 "{ext}"，仅支持 {allowed}'), 400

    quality = max(1, min(100, request.form.get('quality', 80, type=int)))
    max_width = request.form.get('max_width', None, type=int)
    max_height = request.form.get('max_height', None, type=int)

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}{ext}'
    dst_path = OUTPUT_DIR / f'{uid}{ext}'
    file.save(str(src_path))

    try:
        from PIL import Image as _PIL_Image
        img = _PIL_Image.open(str(src_path))

        if ext in ('.jpg', '.jpeg'):
            img = _pil_prepare_for_jpeg(img)

        if max_width or max_height:
            w, h = img.size
            if max_width and w > max_width:
                ratio = max_width / w
                w, h = max_width, int(h * ratio)
            if max_height and h > max_height:
                ratio = max_height / h
                w, h = int(w * ratio), max_height
            img = img.resize((w, h), _PIL_Image.LANCZOS)

        _pil_save_image(img, dst_path, ext, quality)
        img.close()

        if not dst_path.exists() or dst_path.stat().st_size == 0:
            return jsonify(success=False, error='压缩后文件为空'), 500

        return _make_download_response(dst_path, file.filename, ext,
                                       _image_mime(ext), src_path)
    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"图片压缩失败: {e}")
        return jsonify(success=False, error=f'压缩失败: {e}'), 500


# ── API：图片格式互转 ────────────────────────────────────

@app.route('/api/convert/image-format', methods=['POST'])
def api_image_format():
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT_IMAGE:
        allowed = ', '.join(ALLOWED_EXT_IMAGE)
        return jsonify(success=False, error=f'不支持的文件类型 "{ext}"，仅支持 {allowed}'), 400

    target = request.form.get('target_format', 'jpeg').strip().lower()
    quality = max(1, min(100, request.form.get('quality', 90, type=int)))
    bg_color = request.form.get('bg_color', 'white').strip()

    ext_map = {
        'jpeg': '.jpg', 'jpg': '.jpg',
        'png': '.png', 'webp': '.webp',
        'bmp': '.bmp', 'gif': '.gif',
        'tiff': '.tiff', 'tif': '.tiff',
    }
    if target not in ext_map:
        return jsonify(success=False, error=f'不支持的目标格式 "{target}"'), 400

    dst_ext = ext_map[target]
    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}{ext}'
    dst_path = OUTPUT_DIR / f'{uid}{dst_ext}'
    file.save(str(src_path))

    try:
        from PIL import Image as _PIL_Image
        img = _PIL_Image.open(str(src_path))

        if dst_ext in ('.jpg', '.bmp', '.gif') and img.mode in ('RGBA', 'P', 'LA'):
            bg = _PIL_Image.new('RGB', img.size, bg_color)
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                bg.paste(img, mask=img.split()[-1])
            elif img.mode == 'LA':
                bg.paste(img, mask=img.split()[-1])
            img = bg
        elif dst_ext in ('.jpg', '.bmp', '.gif') and img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        _pil_save_image(img, dst_path, dst_ext, quality)
        img.close()

        if not dst_path.exists() or dst_path.stat().st_size == 0:
            return jsonify(success=False, error='转换后文件为空'), 500

        return _make_download_response(dst_path, file.filename, dst_ext,
                                       _image_mime(dst_ext), src_path)
    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"图片格式转换失败: {e}")
        return jsonify(success=False, error=f'转换失败: {e}'), 500


# ── API：图片转 PDF ──────────────────────────────────────

@app.route('/api/convert/images-to-pdf', methods=['POST'])
def api_images_to_pdf():
    files = request.files.getlist('files')
    if not files or len(files) == 0 or all(f.filename == '' for f in files):
        return jsonify(success=False, error='未上传文件'), 400

    valid_files = [f for f in files if f and f.filename]
    if len(valid_files) > MAX_IMAGES_TO_PDF:
        return jsonify(success=False,
                       error=f'最多支持 {MAX_IMAGES_TO_PDF} 张图片'), 400
    if len(valid_files) < 1:
        return jsonify(success=False, error='未选择有效文件'), 400

    uid = uuid.uuid4().hex
    dst_path = OUTPUT_DIR / f'{uid}.pdf'
    src_paths = []

    try:
        from PIL import Image as _PIL_Image

        for f in valid_files:
            f_ext = Path(f.filename).suffix.lower()
            if f_ext not in ALLOWED_EXT_IMAGE:
                for sp in src_paths:
                    _cleanup_file(sp)
                allowed = ', '.join(ALLOWED_EXT_IMAGE)
                return jsonify(success=False,
                               error=f'不支持的文件类型 "{f_ext}"，仅支持 {allowed}'), 400
            sp = UPLOAD_DIR / f'{uid}_{f.filename}'
            f.save(str(sp))
            src_paths.append(sp)

        images = []
        for sp in src_paths:
            img = _PIL_Image.open(str(sp))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            images.append(img)

        if len(images) == 1:
            images[0].save(str(dst_path), 'PDF', resolution=100.0)
        else:
            images[0].save(str(dst_path), 'PDF', save_all=True,
                           append_images=images[1:], resolution=100.0)

        for img in images:
            img.close()

        if not dst_path.exists() or dst_path.stat().st_size == 0:
            return jsonify(success=False, error='生成 PDF 失败'), 500

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=f'combined_{uid[:8]}.pdf',
            mimetype='application/pdf',
        )

        @resp.call_on_close
        def _cleanup_cb(src_paths_=src_paths, dst_path_=dst_path):
            for sp in src_paths_:
                _cleanup_file(sp)
            _cleanup_file(dst_path_)

        return resp

    except Exception as e:
        for sp in src_paths:
            _cleanup_file(sp)
        _cleanup_file(dst_path)
        logger.error(f"图片转 PDF 失败: {e}")
        return jsonify(success=False, error=f'转换失败: {e}'), 500


# ── API：Office 简繁转换 ─────────────────────────────

# OpenCC 转换器单例：s2t (简→繁) / t2s (繁→简)
_zh_converters: dict = {}
_zh_converter_lock = threading.Lock()


def _get_zh_converter(direction: str):
    """获取 OpenCC 转换器单例"""
    if direction in _zh_converters:
        return _zh_converters[direction]
    with _zh_converter_lock:
        if direction not in _zh_converters:
            import opencc
            _zh_converters[direction] = opencc.OpenCC(direction)
    return _zh_converters[direction]


def _zh_convert_docx(src_path: Path, dst_path: Path, convert_fn) -> dict:
    """docx 简繁转换"""
    try:
        from docx import Document
        doc = Document(str(src_path))

        def _conv_paragraphs(paragraphs):
            for p in paragraphs:
                for run in p.runs:
                    if run.text:
                        run.text = convert_fn(run.text)

        _conv_paragraphs(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    _conv_paragraphs(cell.paragraphs)
        for section in doc.sections:
            _conv_paragraphs(section.header.paragraphs)
            _conv_paragraphs(section.footer.paragraphs)
            if section.different_first_page_header_footer:
                _conv_paragraphs(section.first_page_header.paragraphs)
                _conv_paragraphs(section.first_page_footer.paragraphs)

        doc.save(str(dst_path))
        return {"success": True, "error": None}
    except ImportError:
        return {"success": False, "error": "缺少 python-docx 库"}
    except Exception as e:
        return {"success": False, "error": f"docx 转换失败: {e}"}


def _zh_convert_xlsx(src_path: Path, dst_path: Path, convert_fn) -> dict:
    """xlsx 简繁转换"""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(str(src_path))
        n_cells = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value:
                        cell.value = convert_fn(cell.value)
                        n_cells += 1
        wb.save(str(dst_path))
        return {"success": True, "error": None, "cells_converted": n_cells}
    except ImportError:
        return {"success": False, "error": "缺少 openpyxl 库"}
    except Exception as e:
        return {"success": False, "error": f"xlsx 转换失败: {e}"}


def _zh_convert_pptx(src_path: Path, dst_path: Path, convert_fn) -> dict:
    """pptx 简繁转换"""
    try:
        from pptx import Presentation
        prs = Presentation(str(src_path))
        n_runs = 0
        for slide in prs.slides:
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.text:
                            run.text = convert_fn(run.text)
                            n_runs += 1
            if slide.has_notes_slide:
                notes_tf = slide.notes_slide.notes_text_frame
                for para in notes_tf.paragraphs:
                    for run in para.runs:
                        if run.text:
                            run.text = convert_fn(run.text)
                            n_runs += 1
        prs.save(str(dst_path))
        return {"success": True, "error": None, "runs_converted": n_runs}
    except ImportError:
        return {"success": False, "error": "缺少 python-pptx 库"}
    except Exception as e:
        return {"success": False, "error": f"pptx 转换失败: {e}"}


def _zh_preprocess_old_format(src_path: Path, work_dir: Path) -> dict:
    """旧格式 .doc/.xls/.ppt → LibreOffice 转新格式"""
    ext = src_path.suffix.lower()
    new_ext = ZH_OLD_TO_NEW_EXT.get(ext)
    if not new_ext:
        return {"success": False, "new_path": None, "error": f"未知旧格式: {ext}"}

    new_basename = src_path.stem + new_ext
    expected = work_dir / new_basename

    if expected.exists():
        _cleanup_file(expected)

    try:
        os.chmod(src_path, 0o644)
        result = subprocess.run(
            [
                'libreoffice', '--headless', '--norestore',
                '--nofirststartwizard',
                '--convert-to', new_ext[1:].upper(),
                '--outdir', str(work_dir),
                str(src_path.resolve()),
            ],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "new_path": None, "error": "LibreOffice 预处理超时（>300s）"}
    except FileNotFoundError:
        return {"success": False, "new_path": None, "error": "系统中未找到 libreoffice 命令"}
    except Exception as e:
        return {"success": False, "new_path": None, "error": f"LibreOffice 调用失败: {e}"}

    if expected.exists():
        return {"success": True, "new_path": expected, "error": None}

    candidates = list(work_dir.glob(f'*{new_ext}'))
    if candidates:
        return {"success": True, "new_path": candidates[0], "error": None}

    return {
        "success": False, "new_path": None,
        "error": f"LibreOffice 未生成 {new_ext} 文件。stderr: {result.stderr[:200] if result.stderr else '(empty)'}",
    }


def convert_office_zh(src_path: Path, dst_path: Path, direction: str) -> dict:
    """Office 文档简繁转换总入口"""
    if direction not in ZH_VALID_DIRECTIONS:
        return {"success": False, "error": f"无效方向: {direction}"}

    ext = src_path.suffix.lower()
    if ext not in ALLOWED_EXT_OFFICE:
        allowed = ', '.join(sorted(ALLOWED_EXT_OFFICE))
        return {"success": False, "error": f"不支持的文件类型: {ext}，仅支持 {allowed}"}

    try:
        convert_fn = _get_zh_converter(direction).convert
    except Exception as e:
        return {"success": False, "error": f"OpenCC 初始化失败: {e}"}

    work_src = src_path
    converted_from_old = False
    if ext in ZH_OLD_TO_NEW_EXT:
        os.chmod(src_path, 0o644)
        pre = _zh_preprocess_old_format(src_path, dst_path.parent)
        if not pre['success']:
            return {"success": False, "error": pre['error']}
        work_src = pre['new_path']
        converted_from_old = True

    new_ext = work_src.suffix.lower()

    if new_ext == '.docx':
        result = _zh_convert_docx(work_src, dst_path, convert_fn)
    elif new_ext == '.xlsx':
        result = _zh_convert_xlsx(work_src, dst_path, convert_fn)
    elif new_ext == '.pptx':
        result = _zh_convert_pptx(work_src, dst_path, convert_fn)
    else:
        return {"success": False, "error": f"内部错误：未实现的扩展名 {new_ext}"}

    if converted_from_old and work_src.resolve() != dst_path.resolve():
        _cleanup_file(work_src)

    if not result['success']:
        return result

    result['preprocessed'] = converted_from_old
    return result


@app.route('/api/convert/zh-convert', methods=['POST'])
def api_zh_convert():
    """Office 文档简繁转换"""
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400

    direction = request.form.get('direction', '').strip().lower()
    if direction not in ZH_VALID_DIRECTIONS:
        return jsonify(
            success=False,
            error=f'无效方向 "{direction}"，可选: {", ".join(ZH_VALID_DIRECTIONS)}',
        ), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT_OFFICE:
        allowed = ', '.join(sorted(ALLOWED_EXT_OFFICE))
        return jsonify(
            success=False,
            error=f'不支持的文件类型 "{ext}"，仅支持 {allowed}',
        ), 400

    uid = uuid.uuid4().hex
    actual_ext = ZH_OLD_TO_NEW_EXT.get(ext, ext)
    src_path = UPLOAD_DIR / f'{uid}{ext}'
    dst_path = OUTPUT_DIR / f'{uid}{actual_ext}'
    file.save(str(src_path))

    try:
        result = convert_office_zh(src_path, dst_path, direction)
        if not result['success']:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error=result['error']), 500

        if not dst_path.exists() or dst_path.stat().st_size == 0:
            _cleanup_file(src_path)
            _cleanup_file(dst_path)
            return jsonify(success=False, error='转换后文件为空'), 500

        mime_map = {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        mime = mime_map.get(actual_ext, 'application/octet-stream')

        original_stem = Path(file.filename).stem
        suffix = ZH_DIRECTION_SUFFIX[direction]
        download_name = f'{original_stem}{suffix}{actual_ext}'

        resp = send_file(
            str(dst_path),
            as_attachment=True,
            download_name=download_name,
            mimetype=mime,
        )

        @resp.call_on_close
        def _cleanup_cb(src=src_path, dst=dst_path):
            _cleanup_file(src)
            _cleanup_file(dst)

        return resp

    except Exception as e:
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        logger.error(f"简繁转换失败: {e}")
        return jsonify(success=False, error=f'简繁转换失败: {e}'), 500


# ── API：OCR 异步识别 ────────────────────────────────
from services.ocr_service import (create_task, get_task, remove_task,
                                   cleanup_orphaned_tasks, OCR_MAX_FILE_BYTES)


@app.route('/api/ocr/start', methods=['POST'])
def api_ocr_start():
    """提交 OCR 任务，立即��回 task_id"""
    if 'file' not in request.files:
        return jsonify(success=False, error='未上传文件'), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify(success=False, error='文件名为空'), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify(success=False, error='仅支持 .pdf 格式'), 400

    # 检查文件大小
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > OCR_MAX_FILE_BYTES:
        return jsonify(
            success=False,
            error=f'文件大小 {size // 1024 // 1024}MB 超过限制 {OCR_MAX_FILE_BYTES // 1024 // 1024}MB',
        ), 400

    uid = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{uid}.pdf'
    dst_path = OUTPUT_DIR / f'{uid}.docx'
    file.save(str(src_path))

    task_id = create_task(src_path, dst_path, file.filename)
    return jsonify(success=True, task_id=task_id)


@app.route('/api/ocr/status/<task_id>')
def api_ocr_status(task_id):
    """轮询 OCR 任务状态"""
    t = get_task(task_id)
    if not t:
        return jsonify(success=False, error='任务不存在或已过期'), 404
    return jsonify(
        success=True,
        status=t['status'],
        progress=t.get('progress', 0),
        total=t.get('total', 0),
        message=t.get('message', ''),
        error=t.get('error'),
    )


@app.route('/api/ocr/download/<task_id>')
def api_ocr_download(task_id):
    """下载 OCR 结果"""
    t = get_task(task_id)
    if not t:
        return jsonify(success=False, error='任务不存在'), 404
    if t['status'] != 'success':
        return jsonify(success=False, error='任务未完成或已失败'), 400
    dst_path = t['dst_path']
    if not dst_path.exists():
        return jsonify(success=False, error='结果文件已过期'), 404

    resp = send_file(
        str(dst_path),
        as_attachment=True,
        download_name=Path(t['src_filename']).stem + '.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )

    src_path = t['src_path']
    tid = task_id

    @resp.call_on_close
    def _cleanup_on_close():
        _cleanup_file(src_path)
        _cleanup_file(dst_path)
        remove_task(tid)

    return resp


# ═══════════════════════════════════════════════════════════════════
# 初始化 & 应用入口
# ═══════════════════════════════════════════════════════════════════

# OCR 初始化
cleanup_orphaned_tasks()


if __name__ == '__main__':
    logger.info("启动开发服务器...")
    app.run(host='0.0.0.0', port=5000, debug=True)
