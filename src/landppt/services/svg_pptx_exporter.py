"""
SVG → editable PPTX exporter for LandPPT.

Glue layer between LandPPT's per-project ``slides_svg`` data (a list of SVG
strings stored in MongoDB) and the ported ppt-master converter under
``services/svg_to_pptx``.

Public API (used by the v1 export pipeline):
    export_slides_svg_to_pptx(svg_documents, output_path) -> Tuple[bool, str]

The converter is CPU-bound (XML parsing + zip assembly) so we wrap the
synchronous core in ``run_blocking_io`` for use from async request handlers.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .svg_to_pptx import create_pptx_with_native_svg
from ..utils.thread_pool import run_blocking_io

logger = logging.getLogger(__name__)


def _write_svg_documents(svg_documents: List[str], staging_dir: Path) -> List[Path]:
    """Materialize SVG strings as files on disk for the converter to ingest.

    The converter takes ``Path`` inputs (it streams them through XML parsers
    and may rewrite them when finalising icons/images), so writing to disk is
    the cleanest interface and keeps cleanup tied to a TemporaryDirectory.
    """
    paths: List[Path] = []
    for index, svg in enumerate(svg_documents, start=1):
        if not svg or not svg.strip():
            logger.warning("Slide %d has empty SVG content; skipping.", index)
            continue
        # Two-digit prefix preserves slide order (the converter sorts file lists).
        path = staging_dir / f"{index:02d}_slide.svg"
        path.write_text(svg, encoding="utf-8")
        paths.append(path)
    return paths


def _convert_sync(
    svg_documents: List[str],
    output_path: Path,
    canvas_format: Optional[str],
) -> Tuple[bool, str]:
    """Synchronous core: stage SVGs to a temp dir then run the converter."""
    if not svg_documents:
        return False, "No SVG slides provided"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="landppt_svg_") as staging_str:
        staging_dir = Path(staging_str)
        svg_paths = _write_svg_documents(svg_documents, staging_dir)
        if not svg_paths:
            return False, "All SVG slides were empty"

        try:
            ok = create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format=canvas_format,
                verbose=False,
                # Native shapes are the whole point — guarantees editable PPTX.
                use_native_shapes=True,
                # Disable upstream extras LandPPT does not surface.
                transition=None,
                animation=None,
                enable_notes=False,
            )
        except Exception:
            logger.exception("SVG → PPTX conversion crashed")
            return False, "SVG → PPTX conversion crashed; see server logs"

    if not ok:
        return False, "SVG → PPTX conversion failed for one or more slides"
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False, "Converter reported success but produced no output file"

    return True, str(output_path)


async def export_slides_svg_to_pptx(
    svg_documents: List[str],
    output_path: str | Path,
    canvas_format: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Render a list of SVG strings into a single editable PPTX file.

    Args:
        svg_documents: One SVG document per slide, in display order.
        output_path:   Destination path for the .pptx file (parent dirs
                       are created if missing).
        canvas_format: Optional ``CANVAS_FORMATS`` key (e.g. ``'ppt169'``).
                       When None the converter detects from the first SVG's
                       viewBox, falling back to ``'ppt169'`` (1280×720).

    Returns:
        ``(True, output_path)`` on success;
        ``(False, error_message)`` on failure (file is not produced).
    """
    return await run_blocking_io(
        _convert_sync,
        svg_documents,
        Path(output_path),
        canvas_format,
    )
