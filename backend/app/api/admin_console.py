from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

router = APIRouter(tags=["admin-console"])

_CONSOLE_DIR = Path(__file__).resolve().parents[3] / "frontend" / "admin-source-console"


@router.get(
    "/admin/source-console",
    response_class=HTMLResponse,
)
def admin_source_console() -> FileResponse:
    return _file_response("index.html", "text/html")


@router.get(
    "/admin/source-console/admin_source_console.js",
)
def admin_source_console_js() -> Response:
    return _file_response("admin_source_console.js", "application/javascript")


@router.get(
    "/admin/source-console/admin_source_console.css",
)
def admin_source_console_css() -> Response:
    return _file_response("admin_source_console.css", "text/css")


@router.get("/admin/source-conflicts", response_class=HTMLResponse)
def source_conflicts_console() -> FileResponse:
    return _file_response("conflicts.html", "text/html")


@router.get("/admin/source-conflicts/conflicts.js")
def source_conflicts_console_js() -> Response:
    return _file_response("conflicts.js", "application/javascript")


@router.get("/admin/source-conflicts/conflicts.css")
def source_conflicts_console_css() -> Response:
    return _file_response("conflicts.css", "text/css")


@router.get("/admin/source-corpus", response_class=HTMLResponse)
def source_corpus_console() -> FileResponse:
    return _file_response("corpus.html", "text/html")


@router.get("/admin/source-corpus/corpus.js")
def source_corpus_console_js() -> Response:
    return _file_response("corpus.js", "application/javascript")


@router.get("/admin/source-corpus/corpus.css")
def source_corpus_console_css() -> Response:
    return _file_response("corpus.css", "text/css")


def _file_response(filename: str, media_type: str) -> FileResponse:
    path = (_CONSOLE_DIR / filename).resolve()
    if not _is_console_file(path):
        raise HTTPException(status_code=404, detail="Admin console asset not found.")
    return FileResponse(path, media_type=media_type)


def _is_console_file(path: Path) -> bool:
    try:
        path.relative_to(_CONSOLE_DIR.resolve())
    except ValueError:
        return False
    return path.is_file()
