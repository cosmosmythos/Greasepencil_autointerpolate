@echo off
setlocal

REM Fast incremental build — skips cmake configure when build/ already exists.
REM Use this instead of full clean builds to avoid re-downloading nanobind/nanoflann.

set BUILD_DIR=%~dp0build
set PYTHON_DIR=C:\Users\User\AppData\Local\Python\pythoncore-3.14-64

if not exist "%BUILD_DIR%\CMakeCache.txt" (
    echo [build_fast] No CMakeCache.txt found — running full configure first...
    call :configure
)

echo [build_fast] Incremental build (skipping configure)...
cmake --build "%BUILD_DIR%" --config Release --target gp_autointerpolate
if %ERRORLEVEL% neq 0 (
    echo [build_fast] Build failed. Try a clean rebuild: delete build/ and re-run.
    exit /b 1
)

echo.
echo [build_fast] Done. Binary: output\Release\gp_autointerpolate.pyd
exit /b 0

:configure
cmake -S "%~dp0" -B "%BUILD_DIR%" -G "Visual Studio 17 2022" -A x64 ^
    -DPython_ROOT_DIR="%PYTHON_DIR%" ^
    -DPython_EXECUTABLE="%PYTHON_DIR%\python.exe" ^
    -DPython3_ROOT_DIR="%PYTHON_DIR%" ^
    -DPython3_EXECUTABLE="%PYTHON_DIR%\python.exe"
if %ERRORLEVEL% neq 0 (
    echo [build_fast] CMake configure failed.
    exit /b 1
)
