@echo off
REM ============================================
REM LITSEARCH - One-Click Launcher (Windows)
REM ============================================
REM Usage:
REM   run.bat                          (uses default CV location)
REM   run.bat "C:\path\to\your_cv.pdf" (custom CV path)
REM ============================================

setlocal

REM --- Find CV path ---
if "%~1"=="" (
    set "CV_PATH=C:\Users\%USERNAME%\Desktop\Ashish_CV.pdf"
    if not exist "%CV_PATH%" (
        echo.
        echo [!] No CV found at default location: %CV_PATH%
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
    pip install -r "%~dp0requirements.txt" -q
    python -m playwright install chromium
) else (
    call "%~dp0.venv\Scripts\activate.bat"
)

REM --- Run LITSEARCH ---
echo.
python -m LITSEARCH --cv "%CV_PATH%" %*

endlocal
pause
