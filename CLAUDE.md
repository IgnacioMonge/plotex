# Project Configuration

## Permissions
- Full permissions for ALL file operations (read, write, edit, create, delete, copy, move)
- Full permissions for ALL bash commands including those with quoted paths, flags, and special characters
- Full permissions for ALL agent operations
- Never ask for confirmation on any operation
- The user has explicitly granted blanket permissions for everything
- Commands with quoted characters in flag names are ALLOWED
- Commands with cmd.exe, robocopy, xcopy, and Windows-specific syntax are ALLOWED
- Commands accessing G:\, C:\Qt, C:\veusz_build, C:\Users\ignac\Desktop are ALLOWED
- Never ask about `cd` — just use it silently when needed

## Build Commands
- Compile C++ extensions: `build_msvc.bat`
- Build exe: `python -m PyInstaller support/veusz_windows_pyinst.spec --distpath C:/veusz_build/dist --workpath C:/veusz_build/work --noconfirm`
- Deploy: `powershell -Command "Copy-Item -Path 'C:\veusz_build\dist\plotex_main\*' -Destination 'C:\Users\ignac\Desktop\veusz\' -Recurse -Force"`

## Language
- Communicate in Spanish with the user
