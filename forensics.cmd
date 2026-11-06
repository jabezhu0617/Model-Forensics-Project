@echo off
setlocal
set "FORENSICS_PY="
for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do if exist "%%~fD\python.exe" set "FORENSICS_PY=%%~fD\python.exe"
if not defined FORENSICS_PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do if exist "%%~fD\python.exe" set "FORENSICS_PY=%%~fD\python.exe"
if not defined FORENSICS_PY set "FORENSICS_PY=python"
pushd "%~dp0"
if "%~1"=="" (
    "%FORENSICS_PY%" -m forensics --help
) else (
    "%FORENSICS_PY%" -m forensics %*
)
set "FORENSICS_EXIT=%ERRORLEVEL%"
popd
exit /b %FORENSICS_EXIT%
