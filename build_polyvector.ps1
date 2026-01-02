#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build gp_linevector Python wheel for Windows
    
.DESCRIPTION
    Builds the PolyVector-based line art vectorization module for Blender.
    Requires: CMake 3.15+, Python 3.11, OpenCV, Eigen3, Boost
    
.PARAMETER VcpkgRoot
    Path to vcpkg installation (optional, for dependency management)
    
.PARAMETER SkipDependencies
    Skip dependency checks and downloads
    
.EXAMPLE
    .\build_polyvector.ps1
    .\build_polyvector.ps1 -VcpkgRoot C:\vcpkg
#>

param(
    [string]$VcpkgRoot = "",
    [switch]$SkipDependencies = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== Building GP LineVector (PolyVector) ===" -ForegroundColor Cyan

# Check Python version
$pythonVersion = python --version 2>&1
if ($pythonVersion -notmatch "Python 3\.11") {
    Write-Warning "Python 3.11 recommended for Blender 4.3+ compatibility"
    Write-Host "Current: $pythonVersion"
}

# Download missing headers
if (-not $SkipDependencies) {
    Write-Host "`n==> Downloading required headers..." -ForegroundColor Yellow
    
    $svgHeader = "Vectorize/src_polyvector/simple_svg_1.0.0.hpp"
    if (-not (Test-Path $svgHeader)) {
        Write-Host "Downloading simple_svg_1.0.0.hpp..."
        $url = "https://raw.githubusercontent.com/adishavit/simple-svg/master/simple_svg_1.0.0.hpp"
        Invoke-WebRequest -Uri $url -OutFile $svgHeader
        Write-Host "✓ Downloaded simple_svg_1.0.0.hpp" -ForegroundColor Green
    } else {
        Write-Host "✓ simple_svg_1.0.0.hpp already exists" -ForegroundColor Green
    }
}

# Check for dependencies
Write-Host "`n==> Checking dependencies..." -ForegroundColor Yellow

$cmakeFound = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmakeFound) {
    Write-Error "CMake not found. Install from: https://cmake.org/download/"
}
Write-Host "✓ CMake found: $($cmakeFound.Version)" -ForegroundColor Green

# Suggest dependency installation if needed
if (-not $SkipDependencies) {
    Write-Host "`nNote: This build requires OpenCV, Eigen3, and Boost." -ForegroundColor Cyan
    Write-Host "To install via Chocolatey:" -ForegroundColor Cyan
    Write-Host "  choco install opencv eigen boost-msvc-14.3 -y" -ForegroundColor White
    Write-Host "`nOr use vcpkg with -VcpkgRoot parameter" -ForegroundColor Cyan
}

# Create build directory
Write-Host "`n==> Configuring CMake..." -ForegroundColor Yellow
$buildDir = "Vectorize/build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
Set-Location $buildDir

try {
    # Configure CMake
    $cmakeArgs = @(
        "..",
        "-G", "Visual Studio 17 2022",
        "-A", "x64"
    )
    
    # Add vcpkg toolchain if specified
    if ($VcpkgRoot) {
        $toolchain = Join-Path $VcpkgRoot "scripts/buildsystems/vcpkg.cmake"
        if (Test-Path $toolchain) {
            $cmakeArgs += "-DCMAKE_TOOLCHAIN_FILE=$toolchain"
            Write-Host "Using vcpkg toolchain: $toolchain" -ForegroundColor Green
        } else {
            Write-Warning "vcpkg toolchain not found at: $toolchain"
        }
    }
    
    # Add OpenCV path if installed via Chocolatey
    if (Test-Path "C:/tools/opencv/build") {
        $cmakeArgs += "-DOpenCV_DIR=C:/tools/opencv/build"
        Write-Host "Using Chocolatey OpenCV: C:/tools/opencv/build" -ForegroundColor Green
    }
    
    Write-Host "Running: cmake $($cmakeArgs -join ' ')"
    & cmake $cmakeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "CMake configuration failed"
    }
    
    # Build
    Write-Host "`n==> Building C++ module..." -ForegroundColor Yellow
    & cmake --build . --config Release --verbose
    if ($LASTEXITCODE -ne 0) {
        throw "CMake build failed"
    }
    
    Write-Host "`n✓ C++ module built successfully" -ForegroundColor Green
    
    # Verify binary exists
    $binary = Get-ChildItem -Recurse -Filter "gp_linevector*.pyd" | Select-Object -First 1
    if ($binary) {
        Write-Host "✓ Found binary: $($binary.FullName)" -ForegroundColor Green
    } else {
        Write-Warning "Binary not found in build directory"
    }
    
} finally {
    Set-Location ../..
}

# Build Python wheel
Write-Host "`n==> Building Python wheel..." -ForegroundColor Yellow

# Install build dependencies
python -m pip install --upgrade pip setuptools wheel build

# Build wheel
python setup_vectorize.py bdist_wheel

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== Build Complete ===" -ForegroundColor Green
    Write-Host "Wheel created in: dist/" -ForegroundColor Cyan
    
    # List wheels
    $wheels = Get-ChildItem dist/*.whl -ErrorAction SilentlyContinue
    if ($wheels) {
        Write-Host "`nCreated wheels:" -ForegroundColor Cyan
        $wheels | ForEach-Object { Write-Host "  $($_.Name)" -ForegroundColor White }
        
        Write-Host "`nTo install:" -ForegroundColor Cyan
        Write-Host "  pip install dist/$($wheels[0].Name)" -ForegroundColor White
    }
} else {
    Write-Error "Wheel build failed"
}
