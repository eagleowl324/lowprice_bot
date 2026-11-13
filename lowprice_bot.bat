@echo off
chcp 65001 > nul
set "NODE_EXE=C:\Users\UC\AppData\Roaming\Antigravity\bin\agy-node.cmd"
if exist "%NODE_EXE%" (
    call "%NODE_EXE%" "%~dp0lowprice_bot.js" %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python "%~dp0lowprice_bot.py" %*
    exit /b %errorlevel%
)

where node >nul 2>nul
if %errorlevel% equ 0 (
    node "%~dp0lowprice_bot.js" %*
    exit /b %errorlevel%
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lowprice_bot.ps1" %*
exit /b %errorlevel%
