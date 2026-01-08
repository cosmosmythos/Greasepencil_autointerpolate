# Build gp_autointerpolate Python module for Windows
# Requires: CMake 3.15+, Python 3.11, Eigen3 (optional)

$ErrorActionPreference = "Stop"

Write-Host "=== Building GP Auto-Interpolate (FTP-SC) ===" -ForegroundColor Cyan

# Find Python 3.11
Write-Host ""
Write-Host "==> Finding Python 3.11..." -ForegroundColor Yellow
$pythonExe = $null

# Try py launcher first
if (Get-Command py -ErrorAction SilentlyContinue) {
    $version = py -3.11 --version 2>&1
    if ($version -match "Python 3\.11") {
        $pythonExe = py -3.11 -c "import sys; print(sys.executable)" 2>&1
        Write-Host "Found Python 3.11 via py launcher" -ForegroundColor Green
    }
}

# Fallback to python command
if (-not $pythonExe) {
    $version = python --version 2>&1
    if ($version -match "Python 3\.11") {
        $pythonExe = python -c "import sys; print(sys.executable)" 2>&1
        Write-Host "Found Python 3.11: $version" -ForegroundColor Green
    } else {
        Write-Error "Python 3.11 required. Found: $version"
        exit 1
    }
}

Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan

# Check CMake
Write-Host ""
Write-Host "==> Checking CMake..." -ForegroundColor Yellow
$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) {
    Write-Error "CMake not found. Install from: https://cmake.org/download/"
    exit 1
}
Write-Host "CMake found: $($cmake.Version)" -ForegroundColor Green

# Info about optional dependencies
Write-Host ""
Write-Host "==> Optional dependencies..." -ForegroundColor Yellow
Write-Host "Eigen3: Optional (improves Stage 2 performance)" -ForegroundColor Cyan
Write-Host "  Install: choco install eigen -y" -ForegroundColor Gray
Write-Host "nanoflann: Auto-downloaded (header-only)" -ForegroundColor Cyan

# Create build directory
Write-Host ""
Write-Host "==> Configuring CMake..." -ForegroundColor Yellow
$buildDir = "Executable/build"
if (-not (Test-Path $buildDir)) {
    New-Item -ItemType Directory -Path $buildDir | Out-Null
}

$currentDir = Get-Location
Set-Location $buildDir

try {
    # Configure
    cmake .. -G "Visual Studio 17 2022" -A x64 -DPython3_EXECUTABLE="$pythonExe"
    if ($LASTEXITCODE -ne 0) {
        throw "CMake configuration failed"
    }
    
    # Build
    Write-Host ""
    Write-Host "==> Building..." -ForegroundColor Yellow
    cmake --build . --config Release
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed"
    }
    
    Write-Host ""
    Write-Host "Build successful!" -ForegroundColor Green
    
    # Find and copy binary
    $binary = Get-ChildItem -Recurse -Filter "gp_autointerpolate*.pyd" | Select-Object -First 1
    if ($binary) {
        Write-Host "Binary: $($binary.FullName)" -ForegroundColor Green
        
        $outputDir = Join-Path $currentDir "output"
        if (-not (Test-Path $outputDir)) {
            New-Item -ItemType Directory -Path $outputDir | Out-Null
        }
        Copy-Item $binary.FullName -Destination $outputDir -Force
        Write-Host "Copied to: output/" -ForegroundColor Green
    } else {
        Write-Warning "Binary not found"
    }
}
catch {
    Write-Error "Build error: $_"
    Set-Location $currentDir
    exit 1
}
finally {
    Set-Location $currentDir
}

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "Binary: output/gp_autointerpolate.pyd" -ForegroundColor Cyan
