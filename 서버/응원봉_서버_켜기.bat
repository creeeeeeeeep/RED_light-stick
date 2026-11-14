@echo off
rem Crown light-stick relay server launcher.
rem
rem Kept ASCII-only on purpose. Korean text inside a .bat needs chcp,
rem and changing the code page mid-file makes cmd lose its read offset,
rem which eats the first character of following lines. All human-facing
rem messages live in start_server.py instead.

py --version >nul 2>&1
if errorlevel 1 goto nopython

py "%~dp0start_server.py"
exit /b

:nopython
echo.
echo   Python is not installed.
echo.
echo   Download it here, then run this file again:
echo       https://www.python.org/downloads/
echo.
echo   IMPORTANT: check "Add Python to PATH" during setup.
echo.
pause
