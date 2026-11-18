"""Turns a report's HTML into a PDF, and finds the right template for a college.

A college may override a report's layout by adding `reports/<college code>/<name>.html` to the
template folders (a product change, not calculation code). Without one, the default is used.
"""

from typing import Any

from django.http import HttpRequest
from django.template import loader


def template_for(name: str, college_code: str) -> Any:
    return loader.select_template([f"reports/{college_code}/{name}.html", f"reports/{name}.html"])


def render_html(name: str, college_code: str, context: dict[str, Any], request: HttpRequest) -> str:
    context = {**context, "css": _css()}
    return str(template_for(name, college_code).render(context, request))


def _css() -> str:
    from pathlib import Path

    return (Path(__file__).parent / "static" / "reports" / "print.css").read_text(encoding="utf-8")


def pdf_available() -> bool:
    """False when WeasyPrint's native libraries (Pango) are missing on this machine."""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


def to_pdf(html: str) -> bytes:
    import weasyprint

    # No network: a report is self-contained, so nothing is ever fetched while rendering.
    return bytes(weasyprint.HTML(string=html, url_fetcher=_refuse).write_pdf())


def _refuse(url: str, *args: Any, **kwargs: Any) -> Any:
    """Only addresses inside the page itself (data:) are read; anything else is refused."""
    if url.startswith("data:"):
        from weasyprint.urls import default_url_fetcher

        return default_url_fetcher(url, *args, **kwargs)
    raise ValueError("A report may not load outside files")
