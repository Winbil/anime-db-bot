@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%~dp0scripts\project.py" start %*
exit /b %errorlevel%

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python "%~dp0scripts\project.py" start %*
exit /b %errorlevel%

:no_python
echo [anime-db-bot] ERROR: Python 3.11-3.14 is required. 1>&2
exit /b 1
