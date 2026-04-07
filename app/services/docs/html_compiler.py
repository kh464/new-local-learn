from __future__ import annotations

import html
import re


class HtmlCompiler:
    def compile(self, *, title: str, markdown: str) -> str:
        escaped_title = html.escape(title)
        rendered_markdown = self._render_markdown(markdown)
        return (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            f"  <title>{escaped_title}</title>\n"
            "  <style>"
            "body{font-family:Segoe UI,Arial,sans-serif;background:#f3f5f7;color:#18212b;margin:0;line-height:1.6;}"
            "main{max-width:1040px;margin:0 auto;padding:40px 24px 56px;}"
            "header{margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid #d5dde5;}"
            "h1,h2,h3,h4,h5,h6{line-height:1.25;margin:24px 0 12px;}"
            "p{margin:0 0 16px;}"
            "ul{margin:0 0 20px;padding-left:24px;}"
            "li{margin:6px 0;}"
            ".report-content{display:grid;gap:4px;}"
            ".code-block{white-space:pre-wrap;background:#111827;color:#f9fafb;padding:16px;border-radius:12px;overflow:auto;}"
            ".code-block code{font-family:Consolas,'SFMono-Regular',monospace;}"
            ".code-block.mermaid{background:#e8f1ff;color:#16325c;border:1px solid #bfd5ff;}"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            "<main>\n"
            "<header>\n"
            f"<h1>{escaped_title}</h1>\n"
            "</header>\n"
            f"<article class=\"report-content\">{rendered_markdown}</article>\n"
            "</main>\n"
            "</body>\n"
            "</html>\n"
        )

    def _render_markdown(self, markdown: str) -> str:
        blocks: list[str] = []
        paragraph_lines: list[str] = []
        list_items: list[str] = []
        lines = markdown.splitlines()
        index = 0

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return
            blocks.append(f"<p>{html.escape(' '.join(paragraph_lines))}</p>")
            paragraph_lines.clear()

        def flush_list() -> None:
            if not list_items:
                return
            items = "".join(f"<li>{html.escape(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items.clear()

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if stripped.startswith("```"):
                flush_paragraph()
                flush_list()
                language = stripped[3:].strip()
                index += 1
                code_lines: list[str] = []
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    code_lines.append(lines[index])
                    index += 1
                blocks.append(self._render_code_block(language, "\n".join(code_lines)))
                if index < len(lines):
                    index += 1
                continue

            if not stripped:
                flush_paragraph()
                flush_list()
                index += 1
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match is not None:
                flush_paragraph()
                flush_list()
                level = len(heading_match.group(1))
                blocks.append(f"<h{level}>{html.escape(heading_match.group(2))}</h{level}>")
                index += 1
                continue

            if stripped.startswith("- "):
                flush_paragraph()
                list_items.append(stripped[2:].strip())
                index += 1
                continue

            flush_list()
            paragraph_lines.append(stripped)
            index += 1

        flush_paragraph()
        flush_list()
        return "\n".join(blocks)

    def _render_code_block(self, language: str, code: str) -> str:
        escaped_code = html.escape(code)
        if language == "mermaid":
            return f'<pre class="code-block mermaid"><code>{escaped_code}</code></pre>'

        code_class = f' class="language-{html.escape(language)}"' if language else ""
        return f'<pre class="code-block"><code{code_class}>{escaped_code}</code></pre>'
