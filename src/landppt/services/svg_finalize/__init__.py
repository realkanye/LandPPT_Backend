"""svg_finalize — SVG post-processing utilities (icon embedding, image
alignment, tspan flattening, rounded-rect → path).

Ported from ppt-master (https://github.com/hugohe3/ppt-master, MIT License,
Copyright (c) 2025-2026 Hugo He) into LandPPT.  The on-disk orchestrator
script (finalize_svg.py) was dropped — we only use the per-module Python
APIs from the LandPPT pipeline.

Consumers inside LandPPT:
  - svg_to_pptx.use_expander       → embed_icons (in-memory icon expansion)
  - svg_to_pptx.tspan_flattener    → flatten_tspan (in-memory tspan flatten)
  - services.svg_finalizer (LandPPT) → align_embed_images, fix_image_aspect
"""
