"""Text extraction from uploaded documents.

Supports PDF (PyMuPDF), DOCX (python-docx), CSV/TXT/MD (stdlib). Unknown
formats raise ExtractionError, which the worker surfaces on the Document row.
OCR of scanned images is deliberately out of scope for Phase 3.
"""
import csv
import io

import pymupdf  # PyMuPDF (import as pymupdf, not the deprecated `fitz` alias)
from docx import Document as DocxDocument


class ExtractionError(Exception):
    """Raised when a document's format is unsupported or extraction fails."""


def _extract_pdf(data: bytes) -> str:
    parts = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n\n".join(parts)


def _extract_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    paras = [p.text for p in doc.paragraphs]
    return "\n".join(paras)


def _extract_csv(data: bytes) -> str:
    # Render CSV as readable lines so the LLM/chunker see headers + rows.
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(row) for row in reader)


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8-sig")


def _extract_any_text(data: bytes) -> str:
    return data.decode("utf-8-sig")


def extract_text(filename: str, data: bytes) -> str:
    """Dispatch extraction by file extension. Returns extracted text."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    try:
        if ext == "pdf":
            return _extract_pdf(data)
        if ext == "docx":
            return _extract_docx(data)
        if ext == "csv":
            return _extract_csv(data)
        if ext in {"txt", "md", "markdown", "text", "json", "html"}:
            return _extract_txt(data)
        # Fallback: attempt plain-text decode for anything text-ish.
        if not ext:
            return _extract_any_text(data)
        raise ExtractionError(f"Unsupported file type: .{ext}")
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize parse failures
        raise ExtractionError(f"Failed to extract text from {filename}: {exc}") from exc