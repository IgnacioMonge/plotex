@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
set QMAKE_EXE=C:\Qt\6.10.2\msvc2022_64\bin\qmake.exe
set DISTUTILS_USE_SDK=1
set MSSdk=1
cd /d "%~dp0"
python setup.py build_ext --inplace
