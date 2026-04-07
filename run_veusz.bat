@echo off
set PATH=C:\Qt\6.10.2\msvc2022_64\bin;%PATH%
cd /d "%~dp0"
start "" pythonw -c "from veusz import veusz_main; veusz_main.run()"
