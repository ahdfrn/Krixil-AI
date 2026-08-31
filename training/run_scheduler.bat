@echo off
REM Wrapper for Windows Task Scheduler — loads the MSVC/cmake/openssl build environment
REM scheduler.py's underlying training run needs (for llama.cpp/GGUF conversion), then runs the
REM actual scheduler loop. See docs/architecture/learning-and-memory.md Phase 3.

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
set PATH=C:\Program Files\CMake\bin;C:\Program Files\OpenSSL-Win64\bin;%PATH%

cd /d D:\Krixil\training
".venv\Scripts\python.exe" -u scheduler.py >> scheduler.log 2>&1
