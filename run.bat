@echo off
REM ============================================
REM LITSEARCH - One-Click Launcher (Windows)
REM ============================================
REM Usage (from anywhere):
REM   .\run.bat                              (uses default CV)
REM   .\run.bat "C:\path\to\cv.pdf"         (custom CV)
REM   .\run.bat --location Bengaluru --freshness 8
REM ============================================

setlocal

REM --- Always cd to the parent of this folder (Projects/) ---
cd /d "%~dp0.."

REM --- Find CV path (default: Desktop\Ashish_CV.pdf) ---
if "%~1"=="" (
    set "CV_PATH=C:\Users\%USERNAME%\Desktop\Ashish_CV.pdf"
    if not exist "%CV_PATH%" (
        echo.
        echo [!] No CV found at: %CV_PATH%
        echo.
        set /p CV_PATH="Enter path to your CV PDF: "
    )
) else (
    set "CV_PATH=%~1"
)

REM --- Check CV exists ---
if not exist "%CV_PATH%" (
    echo [ERROR] CV file not found: %CV_PATH%
    pause
    exit /b 1
)

REM --- Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM --- Install deps if needed ---
if not exist "%~dp0.venv" (
    echo [*] First run - installing dependencies...
    python -m venv "%~dp0.venv"
    call "%~dp0.venv\Scripts\activate.bat"
    pip install -r "%~dp0LITSEARCH\requirements.txt" -q
    python -m playwright install chromium
) else (
    call "%~dp0.venv\Scripts\activate.bat"
)

REM --- Shift extra args (remove the CV path from positional args) ---
shift
set "EXTRA_ARGS="
:loop
if "%~1"=="" goto done
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto loop
:done

REM --- Run LITSEARCH ---
echo.
python -m LITSEARCH --cv "%CV_PATH%" %EXTRA_ARGS%

endlocal
pause
