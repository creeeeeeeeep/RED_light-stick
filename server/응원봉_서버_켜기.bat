@echo off
chcp 65001 >nul
title 응원봉 서버

rem ---------------------------------------------------------------------------
rem 팬이 더블클릭 한 번으로 서버를 켤 수 있게 하는 파일.
rem
rem 파이썬이 있는지 보고, 없으면 어디서 받는지 알려준다. 있으면 aiohttp 를
rem 확인하고 없을 때만 설치한 뒤 서버를 띄운다.
rem
rem 터미널을 열거나 명령을 칠 일이 없어야 한다 - 여기서 막히면 그 뒤가 다 막힌다.
rem ---------------------------------------------------------------------------

echo.
echo   응원봉 서버를 준비합니다...
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo   [!] 파이썬이 설치되어 있지 않습니다.
    echo.
    echo   아래 주소에서 받아 설치한 뒤 이 파일을 다시 실행해 주세요.
    echo   설치할 때 "Add Python to PATH" 를 꼭 체크하세요.
    echo.
    echo       https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

py -c "import aiohttp" >nul 2>&1
if errorlevel 1 (
    echo   처음 실행이라 필요한 것을 받고 있습니다. 1분쯤 걸립니다...
    echo.
    py -m pip install --quiet --disable-pip-version-check aiohttp
    if errorlevel 1 (
        echo.
        echo   [!] 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.
        echo.
        pause
        exit /b 1
    )
)

cls
echo.
echo   ============================================================
echo.
echo     응원봉 서버가 켜졌습니다.
echo.
echo     이 창을 닫으면 서버도 꺼집니다.
echo     응원봉을 쓰는 동안에는 열어 두세요.
echo.
echo   ============================================================
echo.

py "%~dp0server.py"

echo.
echo   서버가 꺼졌습니다.
pause
