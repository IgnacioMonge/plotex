@echo off
setlocal

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set ISCC64="C:\Program Files\Inno Setup 6\ISCC.exe"

:: Check if Inno Setup is installed
if exist %ISCC% (
    set COMPILER=%ISCC%
    goto :compile
)
if exist %ISCC64% (
    set COMPILER=%ISCC64%
    goto :compile
)

echo.
echo Inno Setup 6 not found. Downloading...
echo.

:: Download Inno Setup
powershell -Command "Invoke-WebRequest -Uri 'https://jrsoftware.org/download.php/is.exe' -OutFile '%TEMP%\innosetup.exe'"
if errorlevel 1 (
    echo ERROR: Failed to download Inno Setup
    echo Please download it manually from https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo Installing Inno Setup...
"%TEMP%\innosetup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
timeout /t 5 /nobreak >nul

if exist %ISCC% (
    set COMPILER=%ISCC%
) else if exist %ISCC64% (
    set COMPILER=%ISCC64%
) else (
    echo ERROR: Inno Setup installation failed
    pause
    exit /b 1
)

:compile
echo.
echo Compiling Plotex installer...
echo.

:: Create output directory
if not exist "C:\veusz_build\installer" mkdir "C:\veusz_build\installer"

:: Compile the installer
%COMPILER% "%~dp0plotex_installer.iss"

if errorlevel 1 (
    echo.
    echo ERROR: Compilation failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Installer created successfully!
echo  Output: C:\veusz_build\installer\Plotex-1.0-Setup.exe
echo ========================================
echo.
pause
