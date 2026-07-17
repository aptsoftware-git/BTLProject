"""
html_writer.py
================
Small helper module providing shared HTML scaffolding (page shell,
escaping) reused by the annotator when generating the annotated and
corrected HTML documents.
"""

from __future__ import annotations

from html import escape as html_escape


BASE_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
       max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #1a1a1a; }
h1 { font-size: 1.4rem; }
.legend { margin-bottom: 24px; padding: 12px 16px; background: #f6f6f6; border-radius: 8px; font-size: 0.9rem; }
.legend span { display: inline-block; padding: 2px 8px; border-radius: 4px; margin-right: 12px; }
.legend span.sev-low { background: #fef3c7; }
.legend span.sev-medium { background: #fed7aa; }
.legend span.sev-high { background: #fecaca; }
.legend span.sev-critical { background: #fca5a5; border: 1px solid #b91c1c; }
.legend span.corrected { background: #b2f2bb; }
.paragraph { margin-bottom: 18px; white-space: pre-wrap; }
mark.sev-low { background: #fef3c7; padding: 1px 2px; border-radius: 3px; cursor: help; }
mark.sev-medium { background: #fed7aa; padding: 1px 2px; border-radius: 3px; cursor: help; }
mark.sev-high { background: #fecaca; padding: 1px 2px; border-radius: 3px; cursor: help; }
mark.sev-critical { background: #fca5a5; outline: 2px solid #b91c1c; padding: 1px 2px; border-radius: 3px; cursor: help; }
mark.corrected { background: #b2f2bb; padding: 1px 2px; border-radius: 3px; }
mark.agreed { outline: 2px solid #444; }
mark.single { outline: 1px dashed #888; }
mark[data-tooltip] { position: relative; }
mark[data-tooltip]:hover::after {
  content: attr(data-tooltip);
  position: absolute; bottom: 125%; left: 0; white-space: pre-wrap;
  background: #222; color: #fff; padding: 8px 10px; border-radius: 6px;
  font-size: 0.8rem; z-index: 10; width: 260px; box-shadow: 0 4px 12px rgba(0,0,0,.2);
}
.meta { color: #666; font-size: 0.85rem; margin-bottom: 4px; }
"""


def page_shell(title: str, body: str, extra_style: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html_escape(title)}</title>
<style>{BASE_STYLE}{extra_style}</style>
</head>
<body>
<h1>{html_escape(title)}</h1>
{body}
</body>
</html>
"""


def escape(text: str) -> str:
    return html_escape(text, quote=True)
