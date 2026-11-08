@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1
set "ROOT=%CD%"

rem This file is used to start the RoadSight website.
rem The first click installs the Python packages from the requirements.txt file.
rem Later clicks only start the website.

rem Find a Python version that is 3.10 or newer.
set "PYEXE="
call :resolve_python
if not defined PYEXE (
  echo Error: Python 3.10 or newer is not installed. Install it and try again.
  echo Download: https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

rem Check if Tesseract is installed. If not, install it.
call :ensure_tesseract

rem Check if ExifTool is installed. If not, install it.
call :ensure_exiftool

rem Make this window see tools that were just installed.
call :prepend_tool_paths

rem First launch: create the Python environment if this Windows one does not exist yet.
if exist "%ROOT%\.venv\Scripts\python.exe" goto venv_ready

echo Installing python packages from requirements.txt...
echo.
"%PYEXE%" -m venv "%ROOT%\.venv"
if errorlevel 1 (
  echo Error: Could not create the Python environment.
  echo.
  pause
  exit /b 1
)
"%ROOT%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%ROOT%\.venv\Scripts\python.exe" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
  echo.
  echo Error: Installation failed.
  echo.
  pause
  exit /b 1
)
echo.
echo Success: Installation finished.

:venv_ready
rem Open the site once the server is accepting connections.
start "RoadSightBrowser" /min powershell.exe -NoProfile -WindowStyle Hidden -Command "for ($i=0; $i -lt 90; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { Start-Process 'http://127.0.0.1:8000/'; exit 0 } } catch { }; Start-Sleep -Seconds 1 }"

cd /d "%ROOT%\src" || (
  echo Error: Could not open the src folder.
  echo.
  pause
  exit /b 1
)

echo Starting RoadSight at http://127.0.0.1:8000
echo To close the RoadSight webapp, close this window.
echo.
"%ROOT%\.venv\Scripts\python.exe" -m fastapi dev webapp.py
echo.
pause
exit /b 0

:resolve_python
where py >nul 2>&1
if errorlevel 1 goto resolve_python_cmd
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
if not defined PYEXE goto resolve_python_cmd
"%PYEXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 set "PYEXE="
if defined PYEXE exit /b 0

:resolve_python_cmd
for /f "delims=" %%I in ('where python 2^>nul') do (
  echo %%I | find /i "\WindowsApps\" >nul
  if errorlevel 1 (
    "%%I" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%%I"
      exit /b 0
    )
  )
)

for %%V in (313 312 311 310) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
      exit /b 0
    )
  )
  if exist "%ProgramFiles%\Python%%V\python.exe" (
    "%ProgramFiles%\Python%%V\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%ProgramFiles%\Python%%V\python.exe"
      exit /b 0
    )
  )
)
exit /b 1

:ensure_tesseract
where tesseract >nul 2>&1
if not errorlevel 1 exit /b 0
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" exit /b 0
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" exit /b 0
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" exit /b 0

echo Webapp needs Tesseract to read numbers on speed-signs.
echo Installing Tesseract...
echo.
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo Error: winget is not available, so Tesseract was not installed.
  echo The webapp will still show the detected features but not the numbers on the speed-signs.
  echo.
  exit /b 0
)
winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
call :prepend_tool_paths
where tesseract >nul 2>&1
if not errorlevel 1 exit /b 0
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" exit /b 0
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" exit /b 0
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" exit /b 0
echo.
echo Error: Tesseract could not be installed.
echo The webapp will still show the detected features but not the numbers on the speed-signs.
echo.
exit /b 0

:ensure_exiftool
where exiftool >nul 2>&1
if not errorlevel 1 exit /b 0
if exist "%ProgramFiles%\ExifTool\exiftool.exe" exit /b 0
if exist "%LOCALAPPDATA%\Programs\ExifTool\exiftool.exe" exit /b 0

echo Webapp needs ExifTool to read latitude and longitude from a .MOV.
echo Installing ExifTool...
echo.
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo Error: winget is not available, so ExifTool was not installed.
  echo The webapp will still detect features, but latitude and longitude will not be shown.
  echo.
  exit /b 0
)
winget install -e --id OliverBetz.ExifTool --silent --accept-package-agreements --accept-source-agreements
call :prepend_tool_paths
where exiftool >nul 2>&1
if not errorlevel 1 exit /b 0
if exist "%ProgramFiles%\ExifTool\exiftool.exe" exit /b 0
if exist "%LOCALAPPDATA%\Programs\ExifTool\exiftool.exe" exit /b 0
echo.
echo Error: ExifTool could not be installed.
echo The webapp will still detect features, but latitude and longitude will not be shown.
echo.
exit /b 0

:prepend_tool_paths
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles%\Tesseract-OCR;%PATH%"
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles(x86)%\Tesseract-OCR;%PATH%"
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "PATH=%LOCALAPPDATA%\Programs\Tesseract-OCR;%PATH%"
if exist "%ProgramFiles%\ExifTool\exiftool.exe" set "PATH=%ProgramFiles%\ExifTool;%PATH%"
if exist "%LOCALAPPDATA%\Programs\ExifTool\exiftool.exe" set "PATH=%LOCALAPPDATA%\Programs\ExifTool;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
exit /b 0


rem # References: this script has been written with the help of AI (chatgpt, Claude, Grok)