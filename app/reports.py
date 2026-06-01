import os
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_excel(data: list[list[str]], topic: str = "report") -> str:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = topic[:31]
    for row in data:
        ws.append(row)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


def generate_html(data: list[list[str]], topic: str = "report") -> str:
    rows_html = ""
    for row in data:
        cells = "".join(f"<td>{c}</td>" for c in row)
        rows_html += f"<tr>{cells}</tr>\n"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{topic}</title>
<style>
body {{ font-family: sans-serif; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
</style></head><body>
<h1>{topic}</h1>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
<table>{rows_html}</table>
</body></html>"""
    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
