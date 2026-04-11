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

:: Clean stale files from dist directory before building installer
:: (PyInstaller --noconfirm replaces files but may leave stale DLLs
::  from earlier builds with different exclude lists)
echo Cleaning dist directory of known stale files...
for %%F in (
    _ssl.pyd libcrypto-1_1.dll libssl-1_1.dll
    libcrypto-3.dll libcrypto-3-x64.dll libssl-3.dll libssl-3-x64.dll
    opengl32sw.dll
) do (
    if exist "C:\veusz_build\dist\plotex_main\%%F" (
        del /q "C:\veusz_build\dist\plotex_main\%%F"
        echo   Removed stale: %%F
    )
)
for %%F in (
    qoffscreen.dll qminimal.dll qtuiotouchplugin.dll
    qtga.dll qwbmp.dll qicns.dll
) do (
    if exist "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\platforms\%%F" (
        del /q "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\platforms\%%F"
        echo   Removed stale plugin: %%F
    )
    if exist "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\generic\%%F" (
        del /q "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\generic\%%F"
        echo   Removed stale plugin: %%F
    )
    if exist "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\imageformats\%%F" (
        del /q "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\plugins\imageformats\%%F"
        echo   Removed stale plugin: %%F
    )
)
for %%F in (Qt6Pdf.dll) do (
    if exist "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\bin\%%F" (
        del /q "C:\veusz_build\dist\plotex_main\PyQt6\Qt6\bin\%%F"
        echo   Removed stale: %%F
    )
)
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
echo  Output: C:\veusz_build\installer\
echo ========================================
echo.
pause
