@echo off
set PATH=C:\Qt\6.10.2\msvc2022_64\bin;C:\Users\ignac\AppData\Roaming\Python\Python311\Scripts;%PATH%
cd /d "%~dp0"
pyinstaller support\veusz_windows_pyinst.spec --distpath dist --workpath build_pyinst --noconfirm
echo.
echo === Build complete ===
echo Executable: dist\veusz_main\veusz.exe
pause
