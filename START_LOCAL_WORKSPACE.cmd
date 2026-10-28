@echo off
setlocal
cd /d "%~dp0"
set "QminiGuidePython=%QMINIGUIDE_PYTHON%"
if defined QminiGuidePython goto validate
if exist ".venv\Scripts\python.exe" (
    set "QminiGuidePython=.venv\Scripts\python.exe"
    goto validate
)
echo Python environment not found. Follow the setup steps in README.md.
echo Existing managed environments can be selected with QMINIGUIDE_PYTHON.
exit /b 2

:validate
if not exist "%QminiGuidePython%" (
    echo Selected Python environment not found. Check QMINIGUIDE_PYTHON.
    exit /b 2
)
"%QminiGuidePython%" -m scripts.run_local_workspace %*
set "QminiGuideExit=%errorlevel%"
if not "%QminiGuideExit%"=="0" pause
exit /b %QminiGuideExit%
