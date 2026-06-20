"""SEO 回归测试 — 验证所有 17 个页面的 SEO 元数据完整性。

策略: 使用 Flask test_client 渲染每个页面, 检查渲染后 HTML 中的 SEO 元素。
SEO 元素由 Jinja 宏动态生成, 不能在源模板中直接检查。

运行方式:
    cd /home/mokch/projects/office-tools
    source venv/bin/activate
    python tests/test_seo.py
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, _SEO_META  # noqa: E402

PAGES: list[tuple[str, str, str]] = [
    # (url, template_filename, slug_in_seo_meta)
    ("/",                 "index.html",         "index"),
    ("/xls-to-xlsx",      "xls_to_xlsx.html",   "xls_to_xlsx"),
    ("/pdf-to-word",      "pdf_to_word.html",   "pdf_to_word"),
    ("/image-compress",   "image_compress.html","image_compress"),
    ("/image-convert",    "image_convert.html", "image_convert"),
    ("/images-to-pdf",    "images_to_pdf.html", "images_to_pdf"),
    ("/hash-check",       "hash_check.html",    "hash_check"),
    ("/base64",           "base64.html",        "base64"),
    ("/json-tool",        "json_tool.html",     "json_tool"),
    ("/timestamp",        "timestamp.html",     "timestamp"),
    ("/pdf-merge",        "pdf_merge.html",     "pdf_merge"),
    ("/pdf-split",        "pdf_split.html",     "pdf_split"),
    ("/pdf-compress",     "pdf_compress.html",  "pdf_compress"),
    ("/qrcode",           "qrcode.html",        "qrcode"),
    ("/pdf-watermark",    "pdf_watermark.html", "pdf_watermark"),
    ("/pdf-encrypt",      "pdf_encrypt.html",   "pdf_encrypt"),
    ("/csv-excel",        "csv_excel.html",     "csv_excel"),
]

TEMPLATES_DIR = ROOT / "templates"
ALL_TOOL_LINKS = sorted({url for url, _, _ in PAGES if url != "/"})

# ── 辅助函数 ──────────────────────────────────


def _has(pattern: str, html: str) -> bool:
    return re.search(pattern, html, re.I) is not None


def _extract_meta(html: str, attr: str, key: str) -> str | None:
    m = re.search(
        rf'<meta\s+(?:{attr})=["\']{re.escape(key)}["\']\s+content=["\']([^"\']*)["\']',
        html, re.I,
    )
    return m.group(1) if m else None


def _extract_link(html: str, rel: str) -> str | None:
    m = re.search(rf'<link\s+rel=["\']{re.escape(rel)}["\']\s+href=["\']([^"\']*)["\']', html, re.I)
    return m.group(1) if m else None


def _extract_jsonld(html: str) -> list[dict]:
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S | re.I,
    )
    out = []
    for b in blocks:
        try:
            out.append(json.loads(b))
        except json.JSONDecodeError:
            pass
    return out


# 渲染缓存 (避免重复渲染)
_HTML_CACHE: dict[str, str] = {}


def _get_html(url: str) -> str:
    if url not in _HTML_CACHE:
        client = app.test_client()
        resp = client.get(url)
        assert resp.status_code == 200, f"{url} 返回 {resp.status_code}"
        _HTML_CACHE[url] = resp.data.decode("utf-8")
    return _HTML_CACHE[url]


# ── 基础类 ──────────────────────────────────


class BasePageTest(unittest.TestCase):
    url: str = ""
    template: str = ""
    slug: str = ""
    html: str = ""

    @classmethod
    def setUpClass(cls):
        cls.html = _get_html(cls.url)


class PageSEOTestMixin:
    """17 个页面的通用 SEO 检查 (基于渲染后 HTML)."""

    url: str
    template: str
    slug: str
    html: str

    def test_01_title_present(self):
        m = re.search(r'<title>(.+?)</title>', self.html, re.I | re.S)
        self.assertIsNotNone(m, f"[{self.url}] 缺少 <title>")
        title = m.group(1).strip()
        self.assertGreater(len(title), 4, f"[{self.url}] <title> 过短: {title!r}")
        self.assertLess(len(title), 70, f"[{self.url}] <title> 过长: {title!r}")
        expected_title = _SEO_META[self.slug]["title"]
        self.assertEqual(title, expected_title, f"[{self.url}] title 与配置不一致: {title!r}")

    def test_02_meta_description(self):
        desc = _extract_meta(self.html, "name", "description")
        self.assertIsNotNone(desc, f"[{self.url}] 缺少 meta description")
        self.assertGreaterEqual(len(desc), 50, f"[{self.url}] description 过短: {desc!r}")
        self.assertLessEqual(len(desc), 200, f"[{self.url}] description 过长: {desc!r}")

    def test_03_meta_keywords(self):
        kw = _extract_meta(self.html, "name", "keywords")
        self.assertIsNotNone(kw, f"[{self.url}] 缺少 meta keywords")
        kws = [k.strip() for k in re.split(r'[,，、]', kw) if k.strip()]
        self.assertGreaterEqual(len(kws), 3, f"[{self.url}] keywords < 3: {kw!r}")

    def test_04_meta_robots(self):
        robots = _extract_meta(self.html, "name", "robots")
        self.assertIsNotNone(robots, f"[{self.url}] 缺少 meta robots")
        self.assertIn("index", robots.lower(), f"[{self.url}] robots 应含 'index'")

    def test_05_canonical(self):
        can = _extract_link(self.html, "canonical")
        self.assertIsNotNone(can, f"[{self.url}] 缺少 canonical")
        u = urlparse(can)
        self.assertIn(u.scheme, ("http", "https"), f"[{self.url}] canonical 非绝对 URL: {can}")
        if self.url == "/":
            self.assertTrue(u.path in ("", "/"), f"[/] canonical path 应为 /")
        else:
            self.assertTrue(
                u.path.rstrip("/") == self.url.rstrip("/"),
                f"[{self.url}] canonical path={u.path} 不匹配",
            )

    def test_06_h1(self):
        self.assertTrue(_has(r'<h1[\s>]', self.html), f"[{self.url}] 缺少 H1")

    def test_07_lang_attr(self):
        self.assertTrue(_has(r'<html[^>]+lang=["\']zh', self.html), f"[{self.url}] 缺 lang=zh")

    def test_08_open_graph(self):
        for k in ("og:title", "og:description", "og:url", "og:type",
                  "og:image", "og:site_name", "og:locale"):
            v = _extract_meta(self.html, "property", k)
            self.assertIsNotNone(v, f"[{self.url}] 缺少 {k}")
            self.assertGreater(len(v), 1, f"[{self.url}] {k} 为空")

    def test_09_twitter_card(self):
        for k in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
            v = _extract_meta(self.html, "name", k)
            self.assertIsNotNone(v, f"[{self.url}] 缺少 {k}")

    def test_10_favicon(self):
        self.assertTrue(
            _has(r'<link[^>]+rel=["\'](icon|shortcut icon)["\']', self.html),
            f"[{self.url}] 缺少 favicon",
        )

    def test_11_apple_touch_icon(self):
        self.assertTrue(
            _has(r'<link[^>]+rel=["\']apple-touch-icon["\']', self.html),
            f"[{self.url}] 缺少 apple-touch-icon",
        )

    def test_12_jsonld_present(self):
        blocks = _extract_jsonld(self.html)
        self.assertGreater(len(blocks), 0, f"[{self.url}] 缺少 JSON-LD 结构化数据")
        for b in blocks:
            self.assertIn("@context", b, f"[{self.url}] JSON-LD 缺 @context")
            self.assertIn("@type", b, f"[{self.url}] JSON-LD 缺 @type")

    def test_13_og_url_matches_canonical(self):
        og = _extract_meta(self.html, "property", "og:url")
        can = _extract_link(self.html, "canonical")
        self.assertIsNotNone(og)
        self.assertIsNotNone(can)
        self.assertEqual(
            urlparse(og).path.rstrip("/"),
            urlparse(can).path.rstrip("/"),
            f"[{self.url}] og:url 与 canonical 不一致",
        )

    def test_14_title_in_og(self):
        title = re.search(r'<title>(.+?)</title>', self.html, re.I | re.S).group(1).strip()
        og_title = _extract_meta(self.html, "property", "og:title")
        self.assertIn(title[:10], og_title, f"[{self.url}] og:title 与 title 差异过大")

    def test_15_description_in_og(self):
        desc = _extract_meta(self.html, "name", "description")
        og_desc = _extract_meta(self.html, "property", "og:description")
        self.assertIn(desc[:30], og_desc, f"[{self.url}] og:description 与 description 差异过大")


def _make_test_class(url: str, tpl: str, slug: str) -> type:
    name = f"TestSEO_{slug}"
    cls = type(
        name,
        (BasePageTest, PageSEOTestMixin),
        {"url": url, "template": tpl, "slug": slug},
    )
    return cls


for _url, _tpl, _slug in PAGES:
    globals()[f"TestSEO_{_slug}"] = _make_test_class(_url, _tpl, _slug)


# ── 全局一致性检查 ───────────────────────────────────


class TestGlobalConsistency(unittest.TestCase):

    def test_all_pages_cover_all_tool_links(self):
        """每个工具页应至少链接到 3 个其他工具页（站内链接建设）"""
        for url, tpl, _slug in PAGES:
            if url == "/":
                continue
            html = _get_html(url)
            other_links = [l for l in ALL_TOOL_LINKS if l != url and f'href="{l}"' in html]
            self.assertGreaterEqual(
                len(other_links), 3,
                f"[{url}] 仅链接到 {len(other_links)} 个其他工具页, 需 ≥ 3",
            )

    def test_favicon_file_exists(self):
        candidates = [ROOT / "static" / "favicon.svg", ROOT / "static" / "favicon.ico"]
        self.assertTrue(
            any(p.exists() for p in candidates),
            f"favicon 文件不存在: {candidates}",
        )

    def test_sitemap_route_defined(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("/sitemap.xml", app_py, "app.py 缺少 /sitemap.xml 路由")
        self.assertIn("/robots.txt", app_py, "app.py 缺少 /robots.txt 路由")

    def test_site_url_constant(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertRegex(app_py, r"SITE_URL\s*=", "app.py 缺少 SITE_URL 常量")

    def test_sitemap_xml_returns_valid_xml(self):
        client = app.test_client()
        resp = client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("xml", resp.headers.get("Content-Type", ""))
        body = resp.data.decode("utf-8")
        self.assertIn("<urlset", body)
        # 应包含全部 17 个 URL (sitemap 含完整域名)
        from app import SITE_URL
        for url, _, slug in PAGES:
            path = _SEO_META[slug]["path"]
            expected = f"<loc>{SITE_URL}{path}</loc>"
            self.assertIn(expected, body, f"sitemap 缺 {url}")

    def test_robots_txt_returns_valid(self):
        client = app.test_client()
        resp = client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        body = resp.data.decode("utf-8")
        self.assertIn("User-agent: *", body)
        self.assertIn("Sitemap:", body)
        self.assertIn("/sitemap.xml", body)

    def test_index_page_lists_all_tools_in_jsonld(self):
        """首页 JSON-LD ItemList 应包含全部 16 个工具"""
        html = _get_html("/")
        blocks = _extract_jsonld(html)
        itemlist = next((b for b in blocks if b.get("@type") == "ItemList"), None)
        self.assertIsNotNone(itemlist, "首页 JSON-LD 缺 ItemList")
        items = itemlist.get("itemListElement", [])
        self.assertGreaterEqual(
            len(items), len(ALL_TOOL_LINKS),
            f"首页 JSON-LD ItemList 仅含 {len(items)} 项, 需 ≥ {len(ALL_TOOL_LINKS)}",
        )

    def test_tool_pages_have_breadcrumb_jsonld(self):
        for url, tpl, _slug in PAGES:
            if url == "/":
                continue
            html = _get_html(url)
            blocks = _extract_jsonld(html)
            self.assertTrue(
                any(b.get("@type") == "BreadcrumbList" for b in blocks),
                f"[{url}] JSON-LD 缺 BreadcrumbList",
            )
            self.assertTrue(
                any(b.get("@type") == "WebApplication" for b in blocks),
                f"[{url}] JSON-LD 缺 WebApplication",
            )

    def test_tool_pages_have_faq_jsonld(self):
        for url, tpl, _slug in PAGES:
            if url == "/":
                continue
            html = _get_html(url)
            blocks = _extract_jsonld(html)
            self.assertTrue(
                any(b.get("@type") == "FAQPage" for b in blocks),
                f"[{url}] JSON-LD 缺 FAQPage",
            )
            # FAQ 应至少 3 个 Q&A
            faq = next((b for b in blocks if b.get("@type") == "FAQPage"), None)
            if faq:
                self.assertGreaterEqual(
                    len(faq.get("mainEntity", [])), 3,
                    f"[{url}] FAQPage Q&A 数量 < 3",
                )

    def test_tool_pages_have_related_tools(self):
        """每个工具页 (非首页) 应有 related-tools 区块。首页是工具索引本身。"""
        for url, tpl, _slug in PAGES:
            if url == "/":
                continue
            html = _get_html(url)
            self.assertIn(
                'class="related-tools"', html,
                f"[{url}] 缺少相关工具区块 (class=related-tools)",
            )

    def test_all_pages_have_footer(self):
        for url, tpl, _slug in PAGES:
            html = _get_html(url)
            self.assertIn(
                'class="site-footer"', html,
                f"[{url}] 缺少 site-footer",
            )

    def test_seo_meta_config_complete(self):
        """_SEO_META 应包含全部 17 个 slug, 且每个有 title/description/keywords/path"""
        self.assertEqual(len(_SEO_META), 17, f"_SEO_META 应有 17 项, 实际 {len(_SEO_META)}")
        for slug, meta in _SEO_META.items():
            for k in ("title", "description", "keywords"):
                self.assertIn(k, meta, f"_SEO_META[{slug!r}] 缺 {k}")
                self.assertGreater(len(meta[k]), 5, f"_SEO_META[{slug!r}][{k}] 过短")
            # path 可以是 "/" (首页)
            self.assertIn("path", meta, f"_SEO_META[{slug!r}] 缺 path")
            self.assertTrue(meta["path"].startswith("/"), f"_SEO_META[{slug!r}] path 应以 / 开头")


# ── HTML 解析健全性 ───────────────────────────────────


class HTMLIntegrityTest(unittest.TestCase):

    def test_all_pages_have_doctype(self):
        for url, _, _ in PAGES:
            html = _get_html(url)
            self.assertTrue(
                html.lstrip().lower().startswith("<!doctype html>"),
                f"[{url}] 缺 <!DOCTYPE html>",
            )

    def test_all_pages_have_charset(self):
        for url, _, _ in PAGES:
            html = _get_html(url)
            self.assertIn(
                'charset="UTF-8"', html,
                f"[{url}] 缺 charset=UTF-8",
            )

    def test_all_pages_have_viewport(self):
        for url, _, _ in PAGES:
            html = _get_html(url)
            self.assertIn(
                'name="viewport"', html,
                f"[{url}] 缺 viewport meta",
            )


if __name__ == "__main__":
    print("=" * 70)
    print(f"SEO 回归测试 — {len(PAGES)} 个页面 (基于渲染后 HTML)")
    print("=" * 70)
    unittest.main(verbosity=2)
