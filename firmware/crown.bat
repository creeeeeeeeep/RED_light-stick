@echo off
rem 크라운 응원봉 작업 스크립트.
rem   그냥 실행하면 명령을 계속 칠 수 있는 모드로 들어갑니다.
rem   crown build      처럼 인자를 주면 그 명령만 하고 끝납니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0crown.ps1" %*
if not "%~1"=="" pause
