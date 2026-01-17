from __future__ import annotations

from typing import Iterable


def _escape_pdf_literal_string(text: str) -> str:
    # PDF literal string escaping for (), \\.
    return text.replace("\\\\", "\\\\\\\\").replace("(", "\\\\(").replace(")", "\\\\)")


def build_simple_text_pdf_bytes(
    *,
    title: str,
    lines: Iterable[str],
    footer_lines: Iterable[str] | None = None,
) -> bytes:
    """Build a minimal deterministic single-page PDF with simple text.

    Notes:
    - No wall-clock timestamps or random IDs.
    - Uses Base14 Helvetica (no embedded fonts).
    - Encodes text as latin-1 with replacement to keep PDF generation dependency-free.
    """

    # A4: 595 x 842 points
    page_w = 595
    page_h = 842

    safe_title = title.encode("latin-1", errors="replace").decode("latin-1")
    safe_lines = [str(line).encode("latin-1", errors="replace").decode("latin-1") for line in lines]

    safe_footer_lines: list[str] = []
    if footer_lines is not None:
        safe_footer_lines = [
            str(line).encode("latin-1", errors="replace").decode("latin-1") for line in footer_lines
        ]

    content_lines: list[str] = [
        "BT",
        "/F1 14 Tf",
        f"50 {page_h - 50} Td ({_escape_pdf_literal_string(safe_title)}) Tj",
        "/F1 10 Tf",
    ]

    # Move down for each line.
    for idx, line in enumerate(safe_lines):
        # First line: move down 22 pts from title baseline.
        if idx == 0:
            content_lines.append(f"0 -22 Td ({_escape_pdf_literal_string(line)}) Tj")
        else:
            content_lines.append(f"0 -14 Td ({_escape_pdf_literal_string(line)}) Tj")

    content_lines.append("ET")

    if safe_footer_lines:
        # Footer block at the bottom-left of the page.
        content_lines.extend(
            [
                "BT",
                "/F1 8 Tf",
                "50 40 Td",
            ]
        )
        for idx, line in enumerate(safe_footer_lines):
            if idx == 0:
                content_lines.append(f"({_escape_pdf_literal_string(line)}) Tj")
            else:
                content_lines.append(f"0 10 Td ({_escape_pdf_literal_string(line)}) Tj")
        content_lines.append("ET")

    # Content stream (latin-1 bytes, deterministic newlines)
    stream = ("\n".join(content_lines) + "\n").encode("latin-1")

    # Build PDF objects with deterministic ordering and offsets.
    parts: list[bytes] = []
    parts.append(b"%PDF-1.4\n")

    offsets: list[int] = [0]  # xref object 0

    def _emit(obj_num: int, body: bytes) -> None:
        offsets.append(sum(len(p) for p in parts))
        parts.append(f"{obj_num} 0 obj\n".encode("ascii"))
        parts.append(body)
        if not body.endswith(b"\n"):
            parts.append(b"\n")
        parts.append(b"endobj\n")

    # 1: Catalog
    _emit(1, b"<< /Type /Catalog /Pages 2 0 R >>\n")
    # 2: Pages
    _emit(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n")
    # 3: Page
    page_obj = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
    ).encode("ascii")
    _emit(3, page_obj)
    # 4: Font
    _emit(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n")
    # 5: Content stream
    content_header = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
    content_body = content_header + stream + b"endstream\n"
    _emit(5, content_body)

    # xref
    xref_start = sum(len(p) for p in parts)
    parts.append(b"xref\n")
    parts.append(f"0 {len(offsets)}\n".encode("ascii"))
    parts.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        parts.append(f"{off:010d} 00000 n \n".encode("ascii"))

    # trailer
    parts.append(b"trailer\n")
    parts.append(f"<< /Size {len(offsets)} /Root 1 0 R >>\n".encode("ascii"))
    parts.append(b"startxref\n")
    parts.append(f"{xref_start}\n".encode("ascii"))
    parts.append(b"%%EOF\n")

    return b"".join(parts)
