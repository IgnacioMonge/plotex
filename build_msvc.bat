@echo off
setlocal enabledelayedexpansion

REM Honour pre-set VCVARS / QMAKE_EXE from the calling environment so
REM CI / contributors with non-default install paths don't have to edit
REM this file. Fall back to the well-known defaults below otherwise.
if not defined VCVARS set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if not defined QMAKE_EXE set QMAKE_EXE=C:\Qt\6.10.2\msvc2022_64\bin\qmake.exe

if not exist %VCVARS% (
    echo ERROR: MSVC 2022 vcvarsall.bat not found at %VCVARS%
    echo Install Visual Studio 2022 Build Tools or edit VCVARS in this script.
    exit /b 1
)
if not exist "%QMAKE_EXE%" (
    echo ERROR: qmake not found at %QMAKE_EXE%
    echo Install Qt 6.10.2 msvc2022_64 or edit QMAKE_EXE in this script.
    exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: python not on PATH.
    exit /b 1
)

call %VCVARS% x64 || exit /b 1
set DISTUTILS_USE_SDK=1
set MSSdk=1
cd /d "%~dp0"
python setup.py build_ext --inplace || exit /b 1
echo.
echo Build complete.
endlocal
