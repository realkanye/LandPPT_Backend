"""
HTML preview builder for the SVG-based slide pipeline.

Embeds each per-slide SVG into a single self-contained HTML document with a
minimal carousel/navigator so the same SVG documents that drive the editable
PPTX export can also be viewed in a browser without further rendering.

Public API:
    build_html_preview(slides_svg, title) -> str
"""

from __future__ import annotations

import html
from typing import Iterable, List


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #38bdf8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Arial, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }}
  header {{
    padding: 16px 24px;
    background: var(--surface);
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  header h1 {{
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }}
  .meta {{ color: var(--muted); font-size: 14px; }}
  main {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }}
  .stage {{
    width: min(100%, 1280px);
    aspect-ratio: 16 / 9;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 24px 60px rgba(0,0,0,0.4);
    position: relative;
  }}
  .slide {{ display: none; width: 100%; height: 100%; }}
  .slide.active {{ display: block; }}
  .slide svg {{ width: 100%; height: 100%; display: block; }}
  nav {{
    padding: 16px 24px;
    background: var(--surface);
    border-top: 1px solid rgba(255,255,255,0.08);
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
  }}
  button {{
    background: rgba(255,255,255,0.06);
    color: var(--text);
    border: 1px solid rgba(255,255,255,0.12);
    padding: 8px 18px;
    border-radius: 8px;
    cursor: pointer;
    font: inherit;
  }}
  button:hover:not(:disabled) {{ background: rgba(255,255,255,0.12); }}
  button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .counter {{
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    min-width: 80px;
    text-align: center;
  }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <span class="meta">{count} slide{plural} · use ← → keys</span>
</header>
<main>
  <div class="stage" id="stage">
{slide_blocks}
  </div>
</main>
<nav>
  <button id="prev">← Prev</button>
  <span class="counter" id="counter">1 / {count}</span>
  <button id="next">Next →</button>
</nav>
<script>
  (function () {{
    const slides = document.querySelectorAll('.slide');
    const counter = document.getElementById('counter');
    const prev = document.getElementById('prev');
    const next = document.getElementById('next');
    let idx = 0;
    function render() {{
      slides.forEach((el, i) => el.classList.toggle('active', i === idx));
      counter.textContent = (idx + 1) + ' / ' + slides.length;
      prev.disabled = idx === 0;
      next.disabled = idx === slides.length - 1;
    }}
    prev.addEventListener('click', () => {{ if (idx > 0) {{ idx--; render(); }} }});
    next.addEventListener('click', () => {{ if (idx < slides.length - 1) {{ idx++; render(); }} }});
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'ArrowLeft' && idx > 0) {{ idx--; render(); }}
      if (e.key === 'ArrowRight' && idx < slides.length - 1) {{ idx++; render(); }}
    }});
    render();
  }})();
</script>
</body>
</html>
"""


def _slide_block(index: int, svg_doc: str) -> str:
    active = " active" if index == 0 else ""
    # Strip any XML declaration so the inline SVG is HTML5-friendly.
    svg = svg_doc.strip()
    if svg.lower().startswith("<?xml"):
        svg = svg.split("?>", 1)[-1].lstrip()
    return f'    <div class="slide{active}">{svg}</div>'


def build_html_preview(*, slides_svg: List[str], title: str = "Presentation") -> str:
    """
    Build a self-contained HTML preview document.

    Args:
        slides_svg: Per-slide SVG documents in display order.
        title:     Presentation title (rendered in the header and <title>).

    Returns:
        A complete HTML5 document as a string.
    """
    safe_title = html.escape(title or "Presentation")
    cleaned = [s for s in (slides_svg or []) if s and s.strip()]
    if not cleaned:
        return f"<!DOCTYPE html><meta charset='utf-8'><title>{safe_title}</title><p>No slides.</p>"

    blocks = "\n".join(_slide_block(i, svg) for i, svg in enumerate(cleaned))
    return _HTML_TEMPLATE.format(
        title=safe_title,
        count=len(cleaned),
        plural="" if len(cleaned) == 1 else "s",
        slide_blocks=blocks,
    )
