"""
Export helpers for PDF and file-based export (moved from web layer).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel

from ..core.config import ai_config
from .pyppeteer_pdf_converter import get_pdf_converter
from ..utils.thread_pool import run_blocking_io

logger = logging.getLogger(__name__)


def _strip_default_port(host: str, scheme: str) -> str:
    host = (host or "").strip()
    scheme = (scheme or "").strip().lower()
    if not host:
        return host

    try:
        parsed = urllib.parse.urlsplit(f"{scheme or 'http'}://{host}")
        hostname = parsed.hostname or host
        port = parsed.port
        if port is None:
            return host
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            if ":" in hostname and not hostname.startswith("["):
                return f"[{hostname}]"
            return hostname
    except Exception:
        return host

    return host


def _normalize_base_url_candidate(raw_url: Optional[str], default_scheme: str = "https") -> Optional[str]:
    value = (str(raw_url).strip() if raw_url is not None else "")
    if not value:
        return None

    if value.startswith("//"):
        value = f"{default_scheme}:{value}"
    elif "://" not in value:
        value = f"{default_scheme}://{value.lstrip('/')}"

    parsed = urllib.parse.urlsplit(value)
    scheme = (parsed.scheme or default_scheme or "https").strip().lower()
    host = (parsed.netloc or "").strip()
    if not host:
        return None

    if "," in host:
        host = host.split(",", 1)[0].strip()
    host = _strip_default_port(host, scheme)
    if not host:
        return None
    return f"{scheme}://{host}"


def _is_loopback_base_url(base_url: Optional[str]) -> bool:
    if not base_url:
        return True
    try:
        parsed = urllib.parse.urlsplit(base_url)
        hostname = (parsed.hostname or "").strip().lower()
        return hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    except Exception:
        return False


def _resolve_export_base_url(http_request: Optional[Request] = None) -> str:
    """Resolve the public base URL used by file-based export renderers."""
    request_candidates: List[str] = []
    config_candidates: List[str] = []

    def add_candidate(target: List[str], raw_url: Optional[str], *, default_scheme: str = "https") -> None:
        normalized = _normalize_base_url_candidate(raw_url, default_scheme=default_scheme)
        if normalized and normalized not in target:
            target.append(normalized)

    try:
        if http_request is not None:
            headers = http_request.headers
            request_scheme = (http_request.url.scheme or "https").strip().lower()

            add_candidate(request_candidates, headers.get("origin"), default_scheme=request_scheme)

            referer = headers.get("referer")
            if referer:
                try:
                    referer_parts = urllib.parse.urlsplit(referer)
                    add_candidate(request_candidates, f"{referer_parts.scheme}://{referer_parts.netloc}", default_scheme=request_scheme)
                except Exception:
                    pass

            forwarded_host = (headers.get("x-forwarded-host") or "").strip()
            forwarded_proto = (headers.get("x-forwarded-proto") or request_scheme).strip().lower()
            forwarded_port = (headers.get("x-forwarded-port") or "").strip()
            if "," in forwarded_host:
                forwarded_host = forwarded_host.split(",", 1)[0].strip()
            if "," in forwarded_proto:
                forwarded_proto = forwarded_proto.split(",", 1)[0].strip()
            if forwarded_host and forwarded_port and ":" not in forwarded_host:
                forwarded_host = f"{forwarded_host}:{forwarded_port}"
            add_candidate(request_candidates, forwarded_host, default_scheme=forwarded_proto or request_scheme)

            host = (headers.get("host") or http_request.url.netloc or "").strip()
            if host:
                add_candidate(request_candidates, host, default_scheme=request_scheme)

            if getattr(http_request, "base_url", None):
                add_candidate(request_candidates, str(http_request.base_url), default_scheme=request_scheme)
    except Exception:
        pass

    try:
        from .url_service import get_current_base_url

        add_candidate(config_candidates, get_current_base_url())
    except Exception:
        pass

    for candidate in request_candidates:
        if not _is_loopback_base_url(candidate):
            return candidate

    for candidate in config_candidates:
        if not _is_loopback_base_url(candidate):
            return candidate

    if request_candidates:
        return request_candidates[0]

    raise ValueError("Unable to resolve export base URL from request headers or app configuration")


def _build_export_app_url(base_url: str, relative_path: str) -> str:
    normalized_path = "/" + (relative_path or "").lstrip("/")
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", normalized_path.lstrip("/"))


_APP_EXPORTABLE_PATH_PREFIXES = (
    "/api/image/view/",
    "/api/image/thumbnail/",
    "/static/",
    "/temp/",
)


def _is_app_exportable_path(path: str) -> bool:
    normalized_path = "/" + str(path or "").lstrip("/")
    return any(normalized_path.startswith(prefix) for prefix in _APP_EXPORTABLE_PATH_PREFIXES)


def _resolve_export_absolute_resource_url(raw_url: str, base_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except Exception:
        return raw_url

    if (parsed.scheme or "").lower() not in {"http", "https"}:
        return raw_url

    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return raw_url

    if not _is_app_exportable_path(parsed.path):
        return raw_url

    relative_path = parsed.path or "/"
    if parsed.query:
        relative_path = f"{relative_path}?{parsed.query}"
    if parsed.fragment:
        relative_path = f"{relative_path}#{parsed.fragment}"
    return _build_export_app_url(base_url, relative_path)


def _file_url_to_path(raw_url: str) -> Optional[Path]:
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        if (parsed.scheme or "").lower() != "file":
            return None

        pathname = urllib.request.url2pathname(parsed.path or "")
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            pathname = f"//{parsed.netloc}{pathname}"

        if os.name == "nt" and pathname.startswith("/") and re.match(r"^/[A-Za-z]:[/\\\\]", pathname):
            pathname = pathname[1:]

        return Path(pathname).resolve(strict=False)
    except Exception:
        return None


def _resolve_export_file_resource_url(raw_url: str, base_url: str) -> str:
    local_path = _file_url_to_path(raw_url)
    if local_path is None:
        return raw_url

    try:
        static_root = (Path(__file__).resolve().parent.parent / "web" / "static").resolve()
        if local_path.is_relative_to(static_root):
            relative_path = local_path.relative_to(static_root).as_posix()
            quoted = urllib.parse.quote(relative_path, safe="/")
            return _build_export_app_url(base_url, f"/static/{quoted}")
    except Exception:
        pass

    try:
        from .image.image_service import get_image_service

        image_service = get_image_service()
        cache_index = getattr(getattr(image_service, "cache_manager", None), "_cache_index", {}) or {}
        for cache_key, cache_info in cache_index.items():
            file_path = getattr(cache_info, "file_path", None)
            if not file_path:
                continue
            try:
                if Path(file_path).resolve(strict=False) == local_path:
                    quoted_key = urllib.parse.quote(str(cache_key), safe="")
                    return _build_export_app_url(base_url, f"/api/image/view/{quoted_key}")
            except Exception:
                continue
    except Exception:
        pass

    return raw_url


def _resolve_export_resource_url(raw_url: str, base_url: str) -> str:
    if not isinstance(raw_url, str):
        return raw_url

    candidate = raw_url.strip()
    if not candidate:
        return raw_url

    lowered = candidate.lower()
    if lowered.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:", "about:")):
        return raw_url
    if lowered.startswith(("http://", "https://")):
        return _resolve_export_absolute_resource_url(candidate, base_url)
    if lowered.startswith("file://"):
        return _resolve_export_file_resource_url(candidate, base_url)
    if candidate.startswith("//"):
        base_scheme = urllib.parse.urlparse(base_url).scheme or "http"
        return f"{base_scheme}:{candidate}"

    joined = urllib.parse.urljoin(f"{base_url.rstrip('/')}/", candidate)
    return joined or candidate


def _rewrite_export_css_urls(css_text: str, base_url: str) -> str:
    if not isinstance(css_text, str) or "url(" not in css_text.lower():
        return css_text

    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        raw_value = (match.group(2) or "").strip()
        suffix = match.group(3)

        quote = ""
        inner = raw_value
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in ("'", '"'):
            quote = raw_value[0]
            inner = raw_value[1:-1]

        absolute_url = _resolve_export_resource_url(inner, base_url)
        return f"{prefix}{quote}{absolute_url}{quote}{suffix}"

    return re.sub(r"(url\(\s*)([^)]+?)(\s*\))", replace_match, css_text, flags=re.IGNORECASE)


def _rewrite_export_srcset(srcset_value: str, base_url: str) -> str:
    if not isinstance(srcset_value, str) or not srcset_value.strip():
        return srcset_value

    rewritten_candidates: List[str] = []
    for candidate in srcset_value.split(","):
        item = candidate.strip()
        if not item:
            continue
        parts = item.split()
        if not parts:
            continue
        parts[0] = _resolve_export_resource_url(parts[0], base_url)
        rewritten_candidates.append(" ".join(parts))
    return ", ".join(rewritten_candidates)


def _html_uses_tailwind_utilities(html_content: str) -> bool:
    if not isinstance(html_content, str) or "class" not in html_content.lower():
        return False

    utility_pattern = re.compile(
        r"^(?:"
        r"container|sr-only|not-sr-only|block|inline|inline-block|inline-flex|flex|inline-grid|grid|hidden|contents|"
        r"absolute|relative|fixed|sticky|static|"
        r"(?:top|right|bottom|left|inset|z)-[\w./\[\]-]+|"
        r"(?:m|mx|my|mt|mr|mb|ml|p|px|py|pt|pr|pb|pl|w|min-w|max-w|h|min-h|max-h|"
        r"gap|space-x|space-y|basis|grow|shrink|order|col|row|"
        r"text|font|leading|tracking|bg|from|via|to|border|rounded|shadow|opacity|"
        r"items|justify|content|self|place|object|overflow|overscroll|whitespace|break|"
        r"aspect|ring|fill|stroke|list|underline|line-clamp|animate|duration|delay|ease|"
        r"scale|rotate|translate|skew)-[\w./:%\[\]-]+|"
        r"(?:prose|antialiased|subpixel-antialiased|uppercase|lowercase|capitalize|truncate|underline|no-underline|italic|not-italic|"
        r"pointer-events-none|pointer-events-auto|select-none|select-text|align-middle|align-top|align-bottom)"
        r")$",
        re.IGNORECASE,
    )

    for match in re.finditer(r'class\s*=\s*["\']([^"\']+)["\']', html_content, flags=re.IGNORECASE):
        class_value = match.group(1) or ""
        for token in re.split(r"\s+", class_value.strip()):
            if token and utility_pattern.match(token):
                return True
    return False


def _strip_unused_tailwind_cdn(html_content: str) -> str:
    if not isinstance(html_content, str) or "cdn.tailwindcss.com" not in html_content.lower():
        return html_content
    if _html_uses_tailwind_utilities(html_content):
        return html_content

    cleaned = re.sub(
        r'<script\b[^>]*src=["\']https://cdn\.tailwindcss\.com(?:/)?[^"\']*["\'][^>]*>\s*</script>',
        '',
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cleaned != html_content:
        cleaned = re.sub(
            r'<script\b(?![^>]*\bsrc=)[^>]*>\s*tailwind\.config\s*=.*?</script>',
            '',
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return cleaned


def _prepare_html_for_file_based_export(html_content: str, base_url: str) -> str:
    if not isinstance(html_content, str) or not html_content.strip():
        return html_content

    prepared = _strip_unused_tailwind_cdn(html_content)
    normalized_base_url = base_url.rstrip("/")
    base_href = f"{normalized_base_url}/"

    if re.search(r"<base\b", prepared, flags=re.IGNORECASE):
        prepared = re.sub(
            r"(<base\b[^>]*\bhref\s*=\s*)(['\"])(.*?)(\2)",
            lambda match: f"{match.group(1)}{match.group(2)}{base_href}{match.group(2)}",
            prepared,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    elif re.search(r"<head\b[^>]*>", prepared, flags=re.IGNORECASE):
        prepared = re.sub(
            r"(<head\b[^>]*>)",
            lambda match: f'{match.group(1)}<base href="{base_href}">',
            prepared,
            count=1,
            flags=re.IGNORECASE,
        )

    def rewrite_attr(attr_name: str, transform) -> None:
        nonlocal prepared
        attr_token = re.escape(attr_name)
        quoted_pattern = rf"((?<![\w:-]){attr_token}\s*=\s*)([\"'])(.*?)(\2)"
        unquoted_pattern = rf"((?<![\w:-]){attr_token}\s*=\s*)(?![\"'])([^\s>]+)"

        prepared = re.sub(
            quoted_pattern,
            lambda match: f"{match.group(1)}{match.group(2)}{transform(match.group(3), normalized_base_url)}{match.group(2)}",
            prepared,
            flags=re.IGNORECASE | re.DOTALL,
        )
        prepared = re.sub(
            unquoted_pattern,
            lambda match: f"{match.group(1)}{transform(match.group(2), normalized_base_url)}",
            prepared,
            flags=re.IGNORECASE,
        )

    for attr in ("src", "href", "poster", "data-src", "data-href", "xlink:href"):
        rewrite_attr(attr, _resolve_export_resource_url)

    rewrite_attr("srcset", _rewrite_export_srcset)
    rewrite_attr("style", _rewrite_export_css_urls)

    prepared = re.sub(
        r"(<style\b[^>]*>)(.*?)(</style>)",
        lambda match: f"{match.group(1)}{_rewrite_export_css_urls(match.group(2), normalized_base_url)}{match.group(3)}",
        prepared,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return prepared


class ImagePPTXExportRequest(BaseModel):
    slides: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[Dict[str, Any]]] = None


ImagePPTXExportRequest.model_rebuild()


async def _generate_pdf_slide_html(slide, slide_number: int, total_slides: int, topic: str) -> str:
    slide_html = slide.get('html_content', '')
    slide_title = slide.get('title', f'第{slide_number}页')

    if slide_html.strip().lower().startswith('<!doctype') or slide_html.strip().lower().startswith('<html'):
        return _clean_html_for_pdf(slide_html, slide_number, total_slides)
    else:
        slide_content = slide_html

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic} - {slide_title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            width: 100%;
            height: 100vh;
            margin: 0;
            padding: 0;
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            overflow: hidden;
        }}

        .slide-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}

        .slide-content {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}

        * {{
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
    </style>
</head>
<body>
    <div class="slide-container">
        <div class="slide-content">
            {slide_content}
        </div>
    </div>
</body>
</html>"""


def _clean_html_for_pdf(original_html: str, slide_number: int, total_slides: int) -> str:
    cleaned_html = original_html

    cleaned_html = re.sub(r'<div[^>]*class="[^"]*navigation[^"]*"[^>]*>.*?</div>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<button[^>]*class="[^"]*nav[^"]*"[^>]*>.*?</button>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<a[^>]*class="[^"]*nav[^"]*"[^>]*>.*?</a>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<button[^>]*fullscreen[^>]*>.*?</button>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)

    pdf_styles = """
    <style>
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }

        html, body {
            width: 100% !important;
            height: 100vh !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }

        .navigation, .nav-btn, .fullscreen-btn, .slide-navigation {
            display: none !important;
        }
    </style>
    """

    cleaned_html = re.sub(r'</head>', pdf_styles + '\n</head>', cleaned_html, flags=re.IGNORECASE)

    return cleaned_html


async def _generate_pdf_with_pyppeteer(project, output_path: str, individual: bool = False) -> bool:
    """Generate PDF using Pyppeteer (Python)"""
    try:
        pdf_converter = get_pdf_converter()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            html_files = []
            for i, slide in enumerate(project.slides_data):
                slide_html = await _generate_pdf_slide_html(
                    slide, i+1, len(project.slides_data), project.topic
                )

                html_file = temp_path / f"slide_{i+1}.html"

                def write_html_file(content, path):
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)

                await run_blocking_io(write_html_file, slide_html, str(html_file))
                html_files.append(str(html_file))

            pdf_dir = temp_path / "pdfs"
            await run_blocking_io(pdf_dir.mkdir)

            logging.info(f"Starting PDF generation for {len(html_files)} files")

            pdf_files = await pdf_converter.convert_multiple_html_to_pdf(
                html_files, str(pdf_dir), output_path
            )

            if pdf_files and os.path.exists(output_path):
                logging.info("Pyppeteer PDF generation successful")
                return True
            else:
                logging.error("Pyppeteer PDF generation failed: No output file created")
                return False

    except Exception as e:
        logging.error(f"Pyppeteer PDF generation failed: {e}")
        return False
