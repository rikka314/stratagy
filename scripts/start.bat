@echo off
setlocal
cd /d "%~dp0\.."
call run.bat %*
exit /b %errorlevel%
