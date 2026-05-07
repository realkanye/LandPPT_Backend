"""svg_to_pptx — SVG → editable-PPTX conversion package.

Ported from ppt-master (https://github.com/hugohe3/ppt-master, MIT License,
Copyright (c) 2025-2026 Hugo He) into LandPPT. The CLI / narration / project
discovery layers were stripped; we expose only the library API used by the
PPT export pipeline.

Public API:
    - convert_svg_to_slide_shapes(): SVG → DrawingML slide XML (low level)
    - create_pptx_with_native_svg(): Build editable PPTX from SVG files (high level)
"""

from .drawingml_converter import convert_svg_to_slide_shapes
from .pptx_builder import create_pptx_with_native_svg

__all__ = [
    'convert_svg_to_slide_shapes',
    'create_pptx_with_native_svg',
]
