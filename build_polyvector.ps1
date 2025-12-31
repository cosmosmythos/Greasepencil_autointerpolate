# Windows PowerShell script to build gp_linevector wheel
# Usage: .\build_polyvector.ps1

param(
    [string]$VcpkgRoot = $env:VCPKG_ROOT,
    [switch]$Clean = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Building GP LineVector Python Wheel" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Check Python version
$pythonVersion = python --version 2>&1
if ($pythonVersion -notmatch "3\.11") {
    Write-Host "WARNING: Python 3.11 is required for Blender 4.3+" -ForegroundColor Yellow
    Write-Host "Current Python: $pythonVersion" -ForegroundColor Yellow
}

# Check vcpkg
if (-not $VcpkgRoot) {
    Write-Host "ERROR: VCPKG_ROOT not set. Please set it or pass -VcpkgRoot parameter" -ForegroundColor Red
    Write-Host "Example: .\build_polyvector.ps1 -VcpkgRoot C:\vcpkg" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path "$VcpkgRoot\scripts\buildsystems\vcpkg.cmake")) {
    Write-Host "ERROR: vcpkg.cmake not found at $VcpkgRoot" -ForegroundColor Red
    exit 1
}

Write-Host "Using vcpkg at: $VcpkgRoot" -ForegroundColor Green

# Check dependencies
Write-Host "`nChecking dependencies..." -ForegroundColor Cyan
$deps = @("opencv", "eigen3", "boost")
foreach ($dep in $deps) {
    $installed = & "$VcpkgRoot\vcpkg.exe" list $dep 2>&1
    if ($installed -match $dep) {
        Write-Host "  ✓ $dep installed" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $dep NOT installed" -ForegroundColor Red
        Write-Host "  Run: .\vcpkg\vcpkg install ${dep}:x64-windows" -ForegroundColor Yellow
        exit 1
    }
}

# Clean if requested
if ($Clean -and (Test-Path "Vectorize\build")) {
    Write-Host "`nCleaning previous build..." -ForegroundColor Cyan
    Remove-Item "Vectorize\build" -Recurse -Force
}

# Create build directory
Write-Host "`nConfiguring CMake..." -ForegroundColor Cyan
Set-Location Vectorize
New-Item -ItemType Directory -Force -Path build | Out-Null
Set-Location build

# Configure with CMake
$cmakeArgs = @(
    "..",
    "-G", "Visual Studio 17 2022",
    "-A", "x64",
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_TOOLCHAIN_FILE=$VcpkgRoot\scripts\buildsystems\vcpkg.cmake"
)

$cmakeConfig = & cmake @cmakeArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: CMake configuration failed" -ForegroundColor Red
    Write-Host $cmakeConfig
    exit 1
}
Write-Host "CMake configuration successful" -ForegroundColor Green

# Build
Write-Host "`nBuilding module..." -ForegroundColor Cyan
$buildOutput = & cmake --build . --config Release 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed" -ForegroundColor Red
    Write-Host $buildOutput
    exit 1
}
Write-Host "Build successful" -ForegroundColor Green

# Check output
$outputFile = "..\output\gp_linevector.pyd"
if (Test-Path $outputFile) {
    $fileSize = (Get-Item $outputFile).Length / 1MB
    Write-Host "  Output: $outputFile" -ForegroundColor Green
    Write-Host "  Size: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Green
} else {
    Write-Host "WARNING: gp_linevector.pyd not found in output directory" -ForegroundColor Yellow
}

# Build wheel
Set-Location ..\..
Write-Host "`nBuilding Python wheel..." -ForegroundColor Cyan
$wheelOutput = & python setup_vectorize.py bdist_wheel 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Wheel build failed" -ForegroundColor Red
    Write-Host $wheelOutput
    exit 1
}

# Show result
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

if (Test-Path "dist\*.whl") {
    $wheel = Get-Item "dist\*.whl" | Select-Object -First 1
    $wheelSize = $wheel.Length / 1MB
    Write-Host "Wheel created: $($wheel.Name)" -ForegroundColor Green
    Write-Host "Size: $([math]::Round($wheelSize, 2)) MB" -ForegroundColor Green
    Write-Host "`nTo install: pip install $($wheel.FullName)" -ForegroundColor Cyan
}
