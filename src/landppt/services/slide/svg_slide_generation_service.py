"""
SVG-based slide generation service for LandPPT.

Replaces the legacy HTML-per-slide pipeline with a structured-SVG pipeline
modelled on ppt-master's Executor role. Each slide is generated as a
self-contained SVG document compliant with the constraints expected by
``services.svg_to_pptx`` (no CSS classes, no rgba, no animations, etc.),
so the same documents can be rendered as an HTML preview AND converted to
a fully editable PPTX without any further translation step.

Output schema per slide (kept simple intentionally for V1):
    Plain SVG string starting with `<svg ...>` and ending with `</svg>`,
    viewBox `0 0 1280 720`, only inline-styled primitives.

Public entrypoint:
    SVGSlideGenerationService(service).generate_slides_svg(project_id) -> List[str]
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..enhanced_ppt_service import EnhancedPPTService


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Distilled from ppt-master executor-base.md + shared-standards.md.
# Conventions are deliberately strict because the downstream svg_to_pptx
# converter does not understand modern SVG features (CSS, masks, animations,
# foreignObject, rgba, group-level opacity, HTML entities).
_SVG_SLIDE_SYSTEM_PROMPT = """You are an expert presentation designer. Your job is to render ONE slide of a presentation as a self-contained SVG document that will later be converted to an editable PowerPoint file.

# Output contract (VERY STRICT)
- Output ONLY the SVG. No prose, no markdown fences, no explanations.
- The first character must be `<` and the last character must be `>` (the closing `</svg>`).
- The root must be `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">`.
- The slide is 1280×720 pixels. Use this coordinate system. Do not use percentages.

# What you may use
- Shapes: `<rect>` (with `rx`/`ry` for rounded), `<circle>`, `<ellipse>`, `<line>`, `<polygon>`, `<polyline>`, `<path>`.
- Text: `<text>` with optional inline `<tspan>` for run-level styling.
- Grouping: `<g id="semantic-name">` to organize related elements.
- Gradients/filters in `<defs>`, referenced via `url(#id)`.
- Inline attributes only: `fill`, `stroke`, `stroke-width`, `stroke-linecap`, `stroke-dasharray`, `font-family`, `font-size`, `font-weight`, `font-style`, `text-anchor`, `letter-spacing`, `text-decoration`, `transform`, `opacity` (on individual shapes only).

# What you MUST NOT use
- No CSS `class` attribute. No `<style>` block. No external stylesheets.
- No `rgba(...)`. Use HEX `fill="#1565C0"` with optional `fill-opacity="0.12"`.
- No `<mask>`, no `<foreignObject>`, no `<symbol>`, no `<use>`, no `@font-face`.
- No animations, no scripts, no `<animate*>`, no `<set>`.
- No HTML entities like `&mdash;` or `&nbsp;`. Use raw Unicode characters.
- Do NOT set `opacity` on a `<g>` group element — apply it on each child instead.
- Do NOT reference any external image URL. If the design needs an image, replace it with a colored shape.

# Visual guidelines
- Backgrounds: a single full-bleed `<rect>` at (0,0,1280,720) for the slide background.
- Typography: prefer `font-family="\\"Microsoft YaHei\\", \\"PingFang SC\\", Arial, sans-serif"`.
  - Page title: 44–56 px, font-weight 700.
  - Section heading: 28–36 px, font-weight 600.
  - Body: 20–24 px, font-weight 400.
  - Annotation / footer: 14–16 px, fill `#888888`.
- Color palette (use these unless the requested style demands otherwise):
  - Primary `#1565C0`, Accent `#00ACC1`, Text `#1F2937`, Muted `#6B7280`, Background `#FFFFFF`, Soft surface `#F3F6FB`.
- Margins: keep at least 80 px clear on the left/right and 60 px top/bottom.
- Visual rhythm: use 1–3 cards / blocks per slide. Avoid clutter. Leave whitespace.
- Decorative accents are welcome (thin underlines, small circles, color dots), but every text element must have actual content.

# Editability requirements (HARD)
- Every text element must be a real `<text>` node — never convert text to paths.
- Every shape must be a real shape primitive — do not output rasterized bitmaps.
- Coordinates must be plain numbers (e.g. `x="80"`), not expressions.

# Anti-patterns to avoid
- Generic "Lorem ipsum" content. Use the slide's actual title/content.
- Empty placeholder boxes with no labels.
- Overlapping text/shape collisions.
- Microscopic text below 14 px.

Produce the SVG now. Remember: ONLY the SVG, nothing else.
"""


def _build_user_prompt(
    *,
    slide_index: int,
    total_slides: int,
    slide_meta: Dict[str, Any],
    project_topic: str,
    project_scenario: str,
    target_audience: str,
    style_hint: str,
    language: str,
) -> str:
    """Assemble the per-slide user message."""
    slide_title = slide_meta.get("title") or slide_meta.get("name") or f"Slide {slide_index}"
    slide_role = slide_meta.get("type") or slide_meta.get("role") or "content"

    # Outline content fields can live under several keys depending on history.
    body_chunks: List[str] = []
    for key in ("content", "summary", "description", "main_points", "key_points", "bullets"):
        value = slide_meta.get(key)
        if not value:
            continue
        if isinstance(value, list):
            body_chunks.extend(str(v).strip() for v in value if str(v).strip())
        elif isinstance(value, str) and value.strip():
            body_chunks.append(value.strip())

    body_text = "\n  - " + "\n  - ".join(body_chunks) if body_chunks else "(no extra detail provided — derive from the title)"

    # Special handling for cover / closing pages
    if slide_index == 1 or slide_role.lower() in {"cover", "title"}:
        layout_hint = (
            "This is the COVER slide. Make a strong title treatment (large title, "
            "subtitle line, color accent bar). Do not use card grids."
        )
    elif slide_index == total_slides or slide_role.lower() in {"ending", "thanks", "closing"}:
        layout_hint = (
            "This is the CLOSING slide. A simple centered 'Thank you' or summary "
            "treatment is appropriate. Keep it minimal."
        )
    elif slide_role.lower() in {"toc", "agenda", "outline"}:
        layout_hint = (
            "This is the AGENDA / TABLE OF CONTENTS slide. List the main sections "
            "vertically with numeric markers."
        )
    else:
        layout_hint = (
            "This is a CONTENT slide. Use a section heading at top, then the main "
            "content (bullet list, two-column blocks, or 2–3 small cards depending "
            "on the amount of information)."
        )

    return f"""Render slide {slide_index} of {total_slides} for the presentation.

# Presentation context
- Topic:           {project_topic}
- Scenario:        {project_scenario}
- Target audience: {target_audience or "general audience"}
- Style hint:      {style_hint or "general"}
- Language:        {language}

# This slide
- Title:  {slide_title}
- Role:   {slide_role}
- Content to convey:{body_text}

# Layout guidance
{layout_hint}

Now output the SVG document for this slide.
"""


# ---------------------------------------------------------------------------
# SVG sanity / repair
# ---------------------------------------------------------------------------

_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_SVG_CLOSE = "</svg>"


def _extract_svg(raw: str) -> Optional[str]:
    """
    Pull the SVG document out of an LLM response.

    The system prompt asks for raw SVG only, but real models sometimes wrap
    it in ```svg fences or chatty preambles. Be lenient.
    """
    if not raw:
        return None
    text = raw.strip()

    # Strip ```svg ... ``` fences if present.
    fence_match = re.search(r"```(?:svg|xml)?\s*(.+?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    open_match = _SVG_OPEN_RE.search(text)
    if not open_match:
        return None
    close_idx = text.lower().rfind(_SVG_CLOSE)
    if close_idx == -1:
        return None
    return text[open_match.start():close_idx + len(_SVG_CLOSE)]


def _ensure_xmlns(svg: str) -> str:
    """Guarantee the root <svg> carries the SVG namespace."""
    if "xmlns=" in svg.split(">", 1)[0]:
        return svg
    return svg.replace(
        "<svg",
        '<svg xmlns="http://www.w3.org/2000/svg"',
        1,
    )


def _normalise_viewbox(svg: str) -> str:
    """Force a 1280×720 viewBox if missing — converter requires this."""
    head = svg.split(">", 1)[0]
    if "viewBox=" in head:
        return svg
    return svg.replace(
        "<svg",
        '<svg viewBox="0 0 1280 720" width="1280" height="720"',
        1,
    )


def sanitize_svg(raw_response: str) -> Optional[str]:
    """
    Best-effort cleanup so an LLM response becomes a valid <svg> document.

    Returns None when the response did not contain an SVG at all.
    """
    extracted = _extract_svg(raw_response)
    if not extracted:
        return None
    return _normalise_viewbox(_ensure_xmlns(extracted))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SVGSlideGenerationService:
    """
    Generate one SVG per outline slide via LLM, persist them on the project,
    and return the list. Drop-in replacement for the legacy HTML-per-slide
    generation path used by ``ppt_creation`` workflow stage.
    """

    def __init__(self, service: "EnhancedPPTService") -> None:
        self._service = service

    # Allow attribute access fallback to the parent service (project_manager,
    # _text_completion_for_role, etc.) so the call sites match the existing
    # service ergonomics.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)

    async def _generate_one_slide_svg(
        self,
        *,
        slide_index: int,
        total_slides: int,
        slide_meta: Dict[str, Any],
        confirmed_requirements: Dict[str, Any],
    ) -> str:
        """Generate a single SVG document. Falls back to a minimal slide on failure."""
        topic = confirmed_requirements.get("topic") or slide_meta.get("title") or "Presentation"
        scenario = confirmed_requirements.get("scenario") or "general"
        target_audience = confirmed_requirements.get("target_audience") or ""
        style_hint = (
            confirmed_requirements.get("custom_style_prompt")
            or confirmed_requirements.get("ppt_style")
            or confirmed_requirements.get("style")
            or ""
        )
        language = confirmed_requirements.get("language") or "zh"

        prompt = _build_user_prompt(
            slide_index=slide_index,
            total_slides=total_slides,
            slide_meta=slide_meta,
            project_topic=str(topic),
            project_scenario=str(scenario),
            target_audience=str(target_audience),
            style_hint=str(style_hint),
            language=str(language),
        )

        try:
            response = await self._service._text_completion_for_role(
                "slide_generation",
                prompt=prompt,
                system_prompt=_SVG_SLIDE_SYSTEM_PROMPT,
                # SVG generation benefits from a slightly cooler temperature.
                temperature=0.4,
            )
        except Exception as exc:
            logger.exception("LLM call failed for slide %d", slide_index)
            return _fallback_slide_svg(
                slide_index, slide_meta.get("title") or f"Slide {slide_index}",
                error=str(exc),
            )

        raw = getattr(response, "content", "") or ""
        svg = sanitize_svg(raw)
        if svg is None:
            logger.warning(
                "LLM did not produce a parseable SVG for slide %d; using fallback",
                slide_index,
            )
            return _fallback_slide_svg(
                slide_index, slide_meta.get("title") or f"Slide {slide_index}",
                error="Model output did not contain <svg>",
            )
        return svg

    async def generate_slides_svg(
        self,
        project_id: str,
        confirmed_requirements: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Run the full per-slide generation loop and persist the result.

        Returns the list of SVG strings. Raises ``ValueError`` if the project
        is missing an outline.
        """
        project = await self._service.project_manager.get_project(project_id)
        if not project or not project.outline:
            raise ValueError(f"Project {project_id} has no outline; cannot generate slides")

        outline = project.outline
        slides_meta = outline.get("slides") or []
        if not slides_meta:
            raise ValueError(f"Project {project_id} outline has no slides")

        if confirmed_requirements is None:
            confirmed_requirements = project.confirmed_requirements or {}

        total = len(slides_meta)
        logger.info("Generating %d SVG slides for project %s", total, project_id)

        produced: List[str] = []
        for idx, slide_meta in enumerate(slides_meta, start=1):
            svg = await self._generate_one_slide_svg(
                slide_index=idx,
                total_slides=total,
                slide_meta=slide_meta if isinstance(slide_meta, dict) else {"title": str(slide_meta)},
                confirmed_requirements=confirmed_requirements,
            )
            produced.append(svg)
            logger.info("  slide %d/%d generated (%d bytes)", idx, total, len(svg))

        # Persist on the project.
        try:
            from ..db_project_manager import DatabaseProjectManager
            db_manager = DatabaseProjectManager()
            await db_manager.save_project_slides_svg(project_id, produced)
        except Exception:
            logger.exception("Failed to persist slides_svg for project %s", project_id)
            raise

        # Mirror onto the in-memory project for downstream consumers.
        project.slides_svg = produced
        project.updated_at = time.time()

        return produced


# ---------------------------------------------------------------------------
# Fallback slide (used when LLM output is unusable)
# ---------------------------------------------------------------------------

_FALLBACK_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect x="0" y="0" width="1280" height="720" fill="#FFFFFF"/>
  <rect x="80" y="80" width="1120" height="6" fill="#1565C0"/>
  <text x="80" y="200" font-family="\\"Microsoft YaHei\\", Arial, sans-serif" font-size="48" font-weight="700" fill="#1F2937">{title}</text>
  <text x="80" y="280" font-family="\\"Microsoft YaHei\\", Arial, sans-serif" font-size="22" fill="#6B7280">Slide {index}</text>
  <text x="80" y="640" font-family="\\"Microsoft YaHei\\", Arial, sans-serif" font-size="14" fill="#B91C1C">[Generation issue: {error}]</text>
</svg>"""


def _fallback_slide_svg(index: int, title: str, *, error: str) -> str:
    """Minimal valid SVG used when LLM output cannot be salvaged."""
    safe_title = (title or f"Slide {index}").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_error = (error or "unknown").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _FALLBACK_TEMPLATE.format(
        title=safe_title[:80],
        index=index,
        error=safe_error[:120],
    )
