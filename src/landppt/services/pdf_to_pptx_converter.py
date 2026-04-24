"""
PDF to PPTX Converter Service for LandPPT

Uses LibreOffice headless mode to convert PDF files to editable PowerPoint
presentations.  No commercial license required — LibreOffice is free and
open-source (MPL-2.0 / LGPL-3.0).

Installation (Linux):
    apt install -y libreoffice

Installation (macOS):
    brew install --cask libreoffice
"""

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PDFToPPTXConverter:
    """
    Converts PDF files to editable PPTX using LibreOffice headless.

    LibreOffice performs structural analysis of the PDF (text extraction,
    font mapping, layout reconstruction) and produces a fully editable .pptx
    file — the same conversion quality as commercial SDKs, at zero cost.
    """

    # Candidate binary paths searched in order
    _BINARY_CANDIDATES = [
        "libreoffice",
        "soffice",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/opt/libreoffice/program/soffice",
        # macOS
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]

    def __init__(self) -> None:
        self._binary: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_binary(self) -> Optional[str]:
        if self._binary is not None:
            return self._binary
        for candidate in self._BINARY_CANDIDATES:
            found = shutil.which(candidate)
            if not found and Path(candidate).is_file():
                found = candidate
            if found:
                self._binary = found
                logger.info("LibreOffice binary located: %s", found)
                return found
        logger.warning(
            "LibreOffice not found. "
            "Install it with:  apt install -y libreoffice"
        )
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if LibreOffice is installed and usable."""
        return self._find_binary() is not None

    async def convert_pdf_to_pptx_async(
        self,
        pdf_path: str,
        output_path: Optional[str] = None,
        timeout: Optional[float] = 120,
    ) -> Tuple[bool, str]:
        """
        Convert a PDF file to an editable PPTX.

        Args:
            pdf_path:    Absolute path to the source PDF.
            output_path: Desired destination for the .pptx file.
                         Defaults to the same directory / stem as the PDF.
            timeout:     Max seconds to wait for LibreOffice (default 120 s).

        Returns:
            (True, output_path)  on success
            (False, error_msg)   on failure
        """
        binary = self._find_binary()
        if binary is None:
            return False, (
                "LibreOffice is not installed. "
                "Run: apt install -y libreoffice"
            )

        pdf_path_obj = Path(pdf_path).resolve()
        if not pdf_path_obj.exists():
            return False, f"Input PDF not found: {pdf_path_obj}"

        # LibreOffice always writes to --outdir; we use a temp dir then move.
        with tempfile.TemporaryDirectory() as tmp_dir:
            cmd = [
                binary,
                "--headless",
                "--norestore",
                "--nofirststartwizard",
                "--convert-to", "pptx",
                "--outdir", tmp_dir,
                str(pdf_path_obj),
            ]

            logger.info(
                "LibreOffice: converting %s → pptx", pdf_path_obj.name
            )
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return (
                        False,
                        f"LibreOffice conversion timed out after {timeout} s",
                    )
            except Exception as exc:
                return False, f"Failed to launch LibreOffice: {exc}"

            if proc.returncode != 0:
                err = stderr.decode(errors="ignore").strip()
                return (
                    False,
                    f"LibreOffice exited with code {proc.returncode}: {err}",
                )

            # LibreOffice names the output <original-stem>.pptx
            generated = Path(tmp_dir) / (pdf_path_obj.stem + ".pptx")
            if not generated.exists() or generated.stat().st_size == 0:
                err = stderr.decode(errors="ignore").strip()
                return False, f"LibreOffice did not produce output: {err}"

            # Move to the requested destination
            if output_path is None:
                output_path = str(pdf_path_obj.with_suffix(".pptx"))
            dest = Path(output_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(generated), str(dest))

        logger.info("PDF → PPTX conversion complete: %s", dest)
        return True, str(dest)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_converter_instance: Optional[PDFToPPTXConverter] = None


def get_pdf_to_pptx_converter() -> PDFToPPTXConverter:
    """Return the process-wide PDFToPPTXConverter instance."""
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = PDFToPPTXConverter()
    return _converter_instance
