# QminiGuide

QminiGuide is a local demo of a WeChat Mini Program and FastAPI assistant for Kazakhstan citizens in China and visitors to Kazakhstan. It demonstrates multilingual chat, translation, document questions, saved cases and checklists, and citizen-consul requests.

Core libraries: [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview), [Pydantic](https://docs.pydantic.dev/latest/), and [HTTPX](https://www.python-httpx.org/). Pinned dependencies are listed in `pyproject.toml` and `uv.lock`.

## Screenshots

Current interface captured in WeChat DevTools on 2026-10-28 with the local demo backend: the assistant home, community guide, and citizen profile. These screenshots show the UI; they are not an evaluation of model output.

| Assistant | Guide | Profile |
| --- | --- | --- |
| ![Assistant](screenshots/home-en-20261028.png) | ![Guide](screenshots/guide-en-20261028.png) | ![Profile](screenshots/profile-en-20261028.png) |

## Run on Windows

Install [Python 3.12](https://docs.python.org/3.12/), then run these commands in PowerShell from the project folder. The setup uses [uv](https://docs.astral.sh/uv/):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv==0.13.4
.\.venv\Scripts\uv.exe sync --locked --extra dev
.\START_LOCAL_WORKSPACE.cmd --mock
```

Keep the backend window open. In WeChat DevTools, open `frontend/wechat-miniprogram` and compile the Mini Program. The local API listens on `127.0.0.1:8000`; press `Ctrl+C` in the backend window to stop it. `--mock` uses a mock AI provider. Photo OCR remains in manual/demo mode unless `--local-ocr` is enabled with Tesseract and its language data configured.

Bundled source snapshots are demonstration material and have not been independently reviewed. Check current travel and legal requirements with official sources. No public reuse license has been selected.

## Selected check results

Recorded local checks from 2026-10-27: 190 selected Python tests passed, one symlink-specific test was skipped because symlink creation was unavailable on Windows, three frontend Node.js suites passed, and Ruff passed. An earlier WeChat DevTools run passed the photo-to-OCR-text-to-chat-to-Kazakh-translation flow; 72 targeted translation tests and 23 frontend runtime scenarios passed. That run record does not identify whether Tesseract handled the photo. On 2026-10-28, two storage-path tests passed, Ruff passed for the changed files, and a `--mock` startup smoke returned HTTP 200 from `/health`; those packaging checks did not rerun the WeChat flow, real-model output, or Tesseract.
