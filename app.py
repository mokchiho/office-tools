#!/usr/bin/env python3
"""
office-tools — 办公效率工具集 Web 应用
"""

import os
import uuid
import time
import shutil
import subprocess
import threading
import concurrent.futures
from pathlib import Path
from flask import (Flask, render_template, request, send_file,
                   jsonify)

# ── 后台定时清理 ──
_CLEANUP_INTERVAL = 600  # 每10分钟
_last_cleanup = time.time()
_cleanup_lock = threading.Lock()


def _periodic_cleanup():
    """清理超过 30 分钟的旧文件 + 过期 OCR 任务"""
    global _last_cleanup
    now = time.time()
    with _cleanup_lock:
        if now - _last_cleanup < _CLEANUP_INTERVAL:
            return
        _last_cleanup = now
    cutoff = now - 1800  # 30分钟
    for d in [UPLOAD_DIR, OUTPUT_DIR]:
        if not d.exists():
            continue
        for f in d.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    _cleanup(f)
            except Exception:
                pass
    # 清理过期 OCR 任务
    with _ocr_tasks_lock:
        expired = [tid for tid, t in _ocr_tasks.items()
                   if t.get('started_at', 0) < cutoff]
        for tid in expired:
            t = _ocr_tasks.pop(tid, None)
            if t:
                _cleanup(t.get('src_path'))
                _cleanup(t.get('dst_path'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'output'

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT_XLS = {'.xls'}
ALLOWED_EXT_PDF = {'.pdf'}

# ── OCR 异步任务 ──
# 任务存储：task_id -> {status, progress, total, message, error, src_path, dst_path, src_filename, started_at}
_ocr_tasks: dict = {}
_ocr_tasks_lock = threading.Lock()
_OCR_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix='ocr'
)
# PP-OCRv6 tiny 引擎单例（进程内仅加载一次）
_ocr_engine = None
_ocr_engine_lock = threading.Lock()

# OCR 输入限制
OCR_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50MB
OCR_MAX_PAGES = 100


def _cleanup(path: Path):
    """删除文件或目录"""
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ── 转换函数 ──────────────────────────────────────────────────

def convert_xls_to_xlsx(src_path: Path, dst_path: Path) -> dict:
    """
    通过 LibreOffice 将 .xls 转换为 .xlsx。
    返回 dict: {"success": bool, "error": str | None}
    """
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
            return {"success": True, "error": None}

        return {
            "success": False,
            "error": f"LibreOffice 未生成目标文件。stderr: {result.stderr}",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "转换超时（>300s）"}
    except FileNotFoundError:
        return {"success": False, "error": "系统中未找到 libreoffice 命令，请安装 LibreOffice"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def convert_pdf_to_docx(src_path: Path, dst_path: Path) -> dict:
    """
    通过 pdf2docx 将 PDF 转换为 DOCX。
    返回 dict: {"success": bool, "error": str | None}
    """
    try:
        from pdf2docx import Converter

        cv = Converter(str(src_path))
        cv.convert(str(dst_path), start=0, end=None)
        cv.close()

        if dst_path.exists() and dst_path.stat().st_size > 0:
            return {"success": True, "error": None}
        return {"success": False, "error": "转换后文件为空"}

    except ImportError:
        return {"success": False, "error": "缺少 pdf2docx 库，请执行: pip install pdf2docx"}
    except Exception as e:
        return {"success": False, "error": f"转换失败: {e}"}


# ── OCR (PP-OCRv6 tiny) ──────────────────────────────────────

def _get_ocr_engine():
    """OCR 引擎单例。首次调用时下载并加载模型。

    使用 RapidOCR (ONNX Runtime) 路线：避免 PaddlePaddle 对老 CPU
    （无 AVX2，如 Intel Xeon E5-2690 v2）不兼容的问题。

    模型默认是 PP-OCRv4 (RapidOCR 内置预转换的 ONNX 模型)，
    中英文识别质量与原 PaddleOCR 几乎一致。
    """
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    with _ocr_engine_lock:
        if _ocr_engine is not None:
            return _ocr_engine
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _update_task(task_id: str, **kwargs):
    """线程安全地更新 OCR 任务状态"""
    with _ocr_tasks_lock:
        t = _ocr_tasks.get(task_id)
        if t:
            t.update(kwargs)


# ── OCR 版式还原算法 ──────────────────────────────────────

def _ocr_group_lines(boxes, texts, y_tol_ratio=0.5):
    """
    把 (box, text) 列表按 Y 中心聚成行。
    同一行的 Y 中心差 < 平均高度 * y_tol_ratio。
    返回 lines = [[(box, text), ...], ...]，每行内按 X 排序。
    box = [x1, y1, x2, y2]
    """
    if not boxes:
        return []
    items = list(zip(boxes, texts))
    # 初始排序：Y 中心、X
    items.sort(key=lambda x: ((x[0][1] + x[0][3]) / 2, x[0][0]))

    lines = []
    current = [items[0]]
    for it in items[1:]:
        y_center = (it[0][1] + it[0][3]) / 2
        avg_h = sum(b[3] - b[1] for b, _ in current) / len(current)
        last_y = (current[-1][0][1] + current[-1][0][3]) / 2
        if abs(y_center - last_y) < max(avg_h * y_tol_ratio, 5):
            current.append(it)
        else:
            current.sort(key=lambda x: x[0][0])
            lines.append(current)
            current = [it]
    if current:
        current.sort(key=lambda x: x[0][0])
        lines.append(current)
    return lines


def _ocr_split_paragraphs(lines, gap_ratio=0.7):
    """
    根据行间 Y 间距把 lines 切分成段落。
    间距 > 平均行高 * gap_ratio → 新段落。
    """
    if not lines:
        return []
    paragraphs = [[lines[0]]]
    for prev, curr in zip(lines, lines[1:]):
        prev_bottom = max(b[3] for b, _ in prev)
        curr_top = min(b[1] for b, _ in curr)
        gap = curr_top - prev_bottom
        prev_h = sum(b[3] - b[1] for b, _ in prev) / len(prev)
        curr_h = sum(b[3] - b[1] for b, _ in curr) / len(curr)
        avg_h = (prev_h + curr_h) / 2
        if avg_h > 0 and gap > avg_h * gap_ratio:
            paragraphs.append([curr])
        else:
            paragraphs[-1].append(curr)
    return paragraphs


def _ocr_format_line(line):
    """
    行内多个文本块按 X 间距智能加空格（保留原排版的横向间距）。
    """
    if len(line) == 1:
        return line[0][1]
    parts = []
    for i, (box, text) in enumerate(line):
        if i > 0:
            prev_x2 = line[i - 1][0][2]
            curr_x1 = box[0]
            gap = curr_x1 - prev_x2
            # 估算字符宽度
            w = box[2] - box[0]
            n = max(len(text), 1)
            char_w = max(w / n, 8)
            # 间距太小 → 1 个空格；间距大 → 多空格
            if gap < char_w * 0.5:
                n_space = 1
            else:
                n_space = max(1, int(gap / char_w))
            parts.append(' ' * n_space)
        parts.append(text)
    return ''.join(parts)


def _ocr_avg_line_height(lines):
    """计算全页平均行高"""
    all_h = [b[3] - b[1] for line in lines for b, _ in line]
    return sum(all_h) / len(all_h) if all_h else 20


import re as _re

_HEADING_PATTERNS = [
    _re.compile(r'第[一二三四五六七八九十百\d]+[页章节]'),          # "第N页/章/节"
    _re.compile(r'【.+】'),                                       # 【XXX】
    _re.compile(r'^([一二三四五六七八九十]+)、'),                 # 一、二、...
    _re.compile(r'^\d+[\.、]\s*\S'),                            # 1. xxx  数字开头
]


def _ocr_classify_paragraph(para_lines, all_lines, para_idx, total_paras):
    """
    综合判断段落类型。
    返回 (style_name, level) 之一：
      - ('Heading 1', None)     一级标题（字号明显大）
      - ('Heading 2', None)     子标题（【XXX】/ "第X页" 模式）
      - ('List Bullet', None)   列表项
    """
    if not para_lines:
        return ('Normal', None)

    first_line = para_lines[0]
    first_text = _ocr_format_line(first_line).strip()
    avg_h = _ocr_avg_line_height(all_lines)
    line_h = sum(b[3] - b[1] for b, _ in first_line) / len(first_line)

    # 1. 字号 > 1.3x 平均 → 可能是标题
    size_big = line_h > avg_h * 1.25

    # 2. 位置判断：是否在页面上方
    all_y_min = min(b[1] for line in all_lines for b, _ in line)
    all_y_max = max(b[3] for line in all_lines for b, _ in line)
    para_y = first_line[0][0][1]
    in_top_quarter = (para_y - all_y_min) < (all_y_max - all_y_min) * 0.3

    # 3. 内容模式判断
    is_h2_pattern = (
        any(p.search(first_text) for p in _HEADING_PATTERNS[:2])
        or bool(_HEADING_PATTERNS[2].match(first_text))  # 一、XX
    )
    is_numbered = bool(_HEADING_PATTERNS[3].match(first_text))

    # 标题优先级
    if size_big and in_top_quarter:
        return ('Heading 1', None)
    if is_h2_pattern:
        return ('Heading 2', None)
    if size_big:
        return ('Heading 1', None)

    # 列表项：段落只有 1 行 + 以 - 1. 开头
    if len(para_lines) == 1 and (
        first_text.startswith(('- ', '•', '·'))
        or is_numbered
        or _HEADING_PATTERNS[2].match(first_text)
    ):
        return ('List Bullet', None)

    # 段落内多行都是列表项格式（- / 数字.）→ 整段是列表
    if len(para_lines) > 1:
        list_count = 0
        for ln in para_lines:
            ln_text = _ocr_format_line(ln).strip()
            if (ln_text.startswith(('- ', '•', '·'))
                    or _HEADING_PATTERNS[3].match(ln_text)
                    or _HEADING_PATTERNS[2].match(ln_text)):
                list_count += 1
        if list_count >= max(2, len(para_lines) * 0.6):
            return ('List Bullet', None)

    return ('Normal', None)


def _ocr_is_table_row(line):
    """
    判断单行是否为表格行：行内 >= 2 个文本块。
    """
    return len(line) >= 2


def _ocr_detect_tables_keep_order(paragraphs):
    """
    在段落列表中查找连续的单行-多列段落，识别为表格。
    返回: (normal_paragraphs, table_groups, tbl_anchor_indices)
      - normal_paragraphs: 普通段落列表
      - table_groups: 表格组列表，每个元素是 [paragraph, ...] 连续表格段落
      - tbl_anchor_indices: 表格的插入位置（在 normal_paras 中的索引，表示该表格插入到此 normal 之后）
    """
    if not paragraphs:
        return [], [], []

    normal = []           # 普通段落
    tables = []           # 表格组
    anchors = []          # 表格插入位置（针对 normal 的索引）
    current_table = []    # 当前累加的表格段落
    current_anchor = -1   # 当前表格的插入位置（最后一个 normal 的索引）

    for para in paragraphs:
        is_table_row = (len(para) == 1 and _ocr_is_table_row(para[0]))
        if is_table_row:
            current_table.append(para)
        else:
            # 结算当前表格
            if current_table:
                col_counts = [len(p[0]) for p in current_table]
                if len(current_table) >= 2 and (max(col_counts) - min(col_counts) <= 1):
                    tables.append(current_table)
                    anchors.append(current_anchor)  # 插入到上一个 normal 后
                else:
                    normal.extend(current_table)
                current_table = []
            normal.append(para)
            current_anchor = len(normal) - 1  # 指向刚刚加入的 normal 索引

    if current_table:
        col_counts = [len(p[0]) for p in current_table]
        if len(current_table) >= 2 and (max(col_counts) - min(col_counts) <= 1):
            tables.append(current_table)
            anchors.append(current_anchor)
        else:
            normal.extend(current_table)

    return normal, tables, anchors


def _ocr_write_table(doc, table_paragraphs):
    """
    把识别出的表格段落写为 docx 表格。
    """
    from docx.shared import Pt
    n_rows = len(table_paragraphs)
    n_cols = max(len(p[0]) for p in table_paragraphs)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.style = 'Light Grid Accent 1'
    for r_idx, para in enumerate(table_paragraphs):
        line = para[0]
        for c_idx, (box, text) in enumerate(line):
            if c_idx < n_cols:
                cell = table.rows[r_idx].cells[c_idx]
                cell.text = text
                # 设置单元格中文字体大小
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(10)


def _ocr_worker(task_id: str, src_path: Path, dst_path: Path):
    """OCR 后台任务（在独立线程中执行）"""
    try:
        _update_task(task_id, status='running', message='正在初始化 OCR 引擎...')
        ocr = _get_ocr_engine()  # 首次会触发模型下载/加载

        from pdf2image import convert_from_path
        from docx import Document

        _update_task(task_id, message='正在解析 PDF 页码...')
        # 先获取总页数（只读取 page count，不渲染）
        from pdf2image.pdf2image import pdfinfo_from_path
        try:
            info = pdfinfo_from_path(str(src_path))
            total_pages = info.get('Pages', 0)
        except Exception:
            total_pages = 0
        if total_pages > OCR_MAX_PAGES:
            _update_task(
                task_id,
                status='failed',
                error=f'PDF 页数 {total_pages} 超过限制 {OCR_MAX_PAGES} 页',
            )
            return
        if total_pages == 0:
            total_pages = 1  # 兜底

        _update_task(task_id, total=total_pages, progress=0,
                     message=f'正在识别 0/{total_pages} 页...')

        images = convert_from_path(str(src_path), dpi=200, fmt='jpeg',
                                   thread_count=2)

        doc = Document()
        # 设置默认中文字体（需本机有对应字体；未找到时回退默认）
        from docx.shared import Pt
        style = doc.styles['Normal']
        style.font.name = 'DejaVu Sans'
        style.font.size = Pt(11)

        for i, img in enumerate(images):
            with _ocr_tasks_lock:
                t = _ocr_tasks.get(task_id)
                if t and t.get('cancel'):
                    _update_task(task_id, status='failed',
                                 error='用户已取消')
                    return

            # 写入临时图片用于 OCR
            tmp_img = dst_path.parent / f'_ocr_{task_id}_p{i}.jpg'
            img.convert('RGB').save(str(tmp_img), 'JPEG', quality=85)
            try:
                result = ocr(str(tmp_img))  # RapidOCR 直接返回 tuple
            finally:
                _cleanup(tmp_img)

            # 提取带坐标的文本块
            # RapidOCR 返回 (detections, scores)
            # detections[i] = [[x1,y1], [x2,y1], [x2,y2], [x1,y2]], text, score
            page_items = []
            if result:
                detections = result[0] if len(result) >= 1 else None
                if detections:
                    for det in detections:
                        if not isinstance(det, (list, tuple)) or len(det) < 2:
                            continue
                        poly = det[0]
                        txt = det[1]
                        if not isinstance(poly, (list, tuple)) or len(poly) < 4:
                            continue
                        if not isinstance(txt, str) or not txt.strip():
                            continue
                        xs = [pt[0] for pt in poly]
                        ys = [pt[1] for pt in poly]
                        box = [min(xs), min(ys), max(xs), max(ys)]
                        page_items.append((box, txt.strip()))

            # 写入 docx
            if i > 0:
                doc.add_page_break()

            if not page_items:
                doc.add_paragraph('')
            else:
                # 1. 按 Y 坐标分行
                boxes = [it[0] for it in page_items]
                texts = [it[1] for it in page_items]
                lines = _ocr_group_lines(boxes, texts)

                # 2. 按行间 Y 间距切段落
                paragraphs = _ocr_split_paragraphs(lines)

                # 2.5 表格检测与切分（保持原顺序）
                normal_paras, table_groups, tbl_anchor = _ocr_detect_tables_keep_order(
                    paragraphs)

                # 3. 按原顺序写入：普通段落 / 表格
                tbl_iter = iter(zip(table_groups, tbl_anchor))
                next_tbl = next(tbl_iter, None)
                for p_idx, para in enumerate(normal_paras):
                    # 检查是否需要在本段前插入表格（anchor == p_idx 表示插到 normal[p_idx] 之前）
                    while next_tbl and next_tbl[1] == p_idx:
                        _ocr_write_table(doc, next_tbl[0])
                        doc.add_paragraph('')
                        next_tbl = next(tbl_iter, None)
                    line_strs = [_ocr_format_line(line) for line in para]
                    text = '\n'.join(line_strs)
                    style, _ = _ocr_classify_paragraph(
                        para, lines, p_idx, len(paragraphs))
                    if style == 'Normal':
                        doc.add_paragraph(text)
                    elif style == 'List Bullet':
                        try:
                            doc.add_paragraph(text, style='List Bullet')
                        except KeyError:
                            doc.add_paragraph(text)
                    else:
                        level = 1 if style == 'Heading 1' else 2
                        try:
                            doc.add_heading(text, level=level)
                        except Exception:
                            doc.add_paragraph(text)
                # 末尾还有表格
                while next_tbl:
                    _ocr_write_table(doc, next_tbl[0])
                    doc.add_paragraph('')
                    next_tbl = next(tbl_iter, None)

            _update_task(
                task_id,
                progress=i + 1,
                message=f'正在识别 {i + 1}/{total_pages} 页...',
            )

        doc.save(str(dst_path))
        _update_task(task_id, status='success',
                     message=f'识别完成，共 {total_pages} 页')

    except ImportError as e:
        _update_task(task_id, status='failed',
                     error=f'缺少依赖库: {e}。请执行: pip install rapidocr_onnxruntime pdf2image Pillow')
    except Exception as e:
        _update_task(task_id, status='failed', error=f'OCR 失败: {e}')


def convert_pdf_ocr_to_docx(src_path: Path, dst_path: Path) -> dict:
    """
    同步入口：实际不直接调用，保留函数签名以兼容 _handle_convert 风格。
    OCR 任务通过 /api/ocr/start 走异步流程。
    """
    return {"success": False, "error": "OCR 任务请通过 /api/ocr/start 提交"}


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
        _cleanup(original_src)
        _cleanup(original_dst)

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
            return jsonify(success=False, error=result['error']), 500
        return _make_download_response(dst_path, file.filename, new_ext, mime_type, src_path)
    except Exception as e:
        _cleanup(src_path)
        _cleanup(dst_path)
        return jsonify(success=False, error=str(e)), 500


# ── 页面路由 ──────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/xls-to-xlsx')
def xls_to_xlsx_page():
    return render_template('xls_to_xlsx.html')


@app.route('/pdf-to-word')
def pdf_to_word_page():
    return render_template('pdf_to_word.html')


# ── API 路由 ──────────────────────────────────────────────────

@app.route('/api/convert/xls-to-xlsx', methods=['POST'])
def api_xls_to_xlsx():
    return _handle_convert(ALLOWED_EXT_XLS, convert_xls_to_xlsx, '.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/api/convert/pdf-to-docx', methods=['POST'])
def api_pdf_to_docx():
    return _handle_convert(ALLOWED_EXT_PDF, convert_pdf_to_docx, '.docx',
                           'application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# ── OCR API（异步）─────────────────────────────────────

@app.route('/api/ocr/start', methods=['POST'])
def api_ocr_start():
    """提交 OCR 任务，立即返回 task_id"""
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

    task_id = uuid.uuid4().hex
    src_path = UPLOAD_DIR / f'{task_id}.pdf'
    dst_path = OUTPUT_DIR / f'{task_id}.docx'
    file.save(str(src_path))

    with _ocr_tasks_lock:
        _ocr_tasks[task_id] = {
            'status': 'pending',
            'progress': 0,
            'total': 0,
            'message': '已入队，等待识别...',
            'error': None,
            'src_path': src_path,
            'dst_path': dst_path,
            'src_filename': file.filename,
            'started_at': time.time(),
            'cancel': False,
        }

    _OCR_EXECUTOR.submit(_ocr_worker, task_id, src_path, dst_path)
    return jsonify(success=True, task_id=task_id)


@app.route('/api/ocr/status/<task_id>')
def api_ocr_status(task_id):
    """轮询 OCR 任务状态"""
    with _ocr_tasks_lock:
        t = _ocr_tasks.get(task_id)
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
    with _ocr_tasks_lock:
        t = _ocr_tasks.get(task_id)
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
        _cleanup(src_path)
        _cleanup(dst_path)
        with _ocr_tasks_lock:
            _ocr_tasks.pop(tid, None)

    return resp


# ── 全局 ──────────────────────────────────────────────────────

@app.after_request
def cleanup_after_request(response):
    """全局：定时清理过期文件"""
    _periodic_cleanup()
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
