@echo off
setlocal
cd /d "%~dp0\.."
call run.bat --setup-only %*
exit /b %errorlevel%
