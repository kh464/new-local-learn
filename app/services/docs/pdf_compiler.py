from __future__ import annotations

import re
import textwrap


class PdfCompiler:
    _PAGE_WIDTH = 612
    _PAGE_HEIGHT = 792
    _LEFT_MARGIN = 72
    _TOP_MARGIN = 760
    _BOTTOM_MARGIN = 56
    _LINE_HEIGHT = 16
    _WRAP_WIDTH = 88

    def compile(self, *, title: str, markdown: str) -> bytes:
        lines = self._prepare_lines(title=title, markdown=markdown)
        pages = self._paginate_lines(lines)
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]

        font_object_id = 3 + (len(pages) * 2)
        page_object_ids = [3 + (index * 2) for index in range(len(pages))]
        kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("latin-1"))

        for index, page_lines in enumerate(pages):
            page_object_id = 3 + (index * 2)
            content_object_id = page_object_id + 1
            content_stream = self._build_content_stream(page_lines)
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self._PAGE_WIDTH} {self._PAGE_HEIGHT}] "
                    f"/Contents {content_object_id} 0 R /Resources << /Font << /F1 {font_object_id} 0 R >> >> >>"
                ).encode("latin-1")
            )
            objects.append(
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
                + content_stream
                + b"\nendstream"
            )

        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        return self._build_pdf(objects)

    def _build_content_stream(self, lines: list[str]) -> bytes:
        commands = [
            "BT",
            "/F1 12 Tf",
            f"{self._LINE_HEIGHT} TL",
            f"{self._LEFT_MARGIN} {self._TOP_MARGIN} Td",
        ]
        for index, line in enumerate(lines):
            escaped = self._escape_pdf_text(line)
            commands.append(f"({escaped}) Tj")
            if index != len(lines) - 1:
                commands.append("T*")
        commands.append("ET")
        return "\n".join(commands).encode("latin-1", errors="ignore")

    def _prepare_lines(self, *, title: str, markdown: str) -> list[str]:
        prepared = [title, ""]
        in_code_block = False
        code_language = ""

        for raw_line in markdown.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                if in_code_block:
                    in_code_block = False
                    code_language = ""
                    prepared.append("")
                else:
                    in_code_block = True
                    code_language = stripped[3:].strip()
                    prepared.append(f"[code{': ' + code_language if code_language else ''}]")
                continue

            if in_code_block:
                prepared.extend(self._wrap_line(f"    {raw_line}"))
                continue

            if not stripped:
                prepared.append("")
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match is not None:
                prepared.extend(self._wrap_line(heading_match.group(2).strip().upper()))
                prepared.append("")
                continue

            if stripped.startswith("- "):
                prepared.extend(self._wrap_line(f"* {stripped[2:].strip()}"))
                continue

            prepared.extend(self._wrap_line(stripped))

        return prepared

    def _wrap_line(self, value: str) -> list[str]:
        if not value:
            return [""]
        return textwrap.wrap(
            value,
            width=self._WRAP_WIDTH,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=False,
        ) or [value]

    def _paginate_lines(self, lines: list[str]) -> list[list[str]]:
        lines_per_page = ((self._TOP_MARGIN - self._BOTTOM_MARGIN) // self._LINE_HEIGHT) + 1
        pages: list[list[str]] = []
        for start in range(0, len(lines), lines_per_page):
            pages.append(lines[start : start + lines_per_page])
        return pages or [[""]]

    def _build_pdf(self, objects: list[bytes]) -> bytes:
        parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(sum(len(part) for part in parts))
            parts.append(f"{index} 0 obj\n".encode("latin-1"))
            parts.append(obj)
            parts.append(b"\nendobj\n")
        xref_offset = sum(len(part) for part in parts)
        parts.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        parts.append(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            parts.append(f"{offset:010d} 00000 n \n".encode("latin-1"))
        parts.append(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
            ).encode("latin-1")
        )
        return b"".join(parts)

    def _escape_pdf_text(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
