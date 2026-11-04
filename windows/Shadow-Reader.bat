@echo off
setlocal
cd /d "%~dp0"
title Shadow Reader

rem Use the Python that comes with this download; fall back to a Python installed on the system.
set "PY=%~dp0python\python.exe"
if not exist "%PY%" (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Please download the full Shadow Reader zip again and extract all files.
    echo.
    pause
    exit /b 1
  )
  set "PY=python"
)

"%PY%" server.py
if errorlevel 1 (
  echo.
  echo Shadow Reader stopped with an error. The message above says why.
  pause
)
