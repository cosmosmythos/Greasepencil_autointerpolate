"""
Setup script for building gp_autointerpolate wheel
This wraps the CMake-built C++ extension into a proper Python wheel
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import os
import shutil
from pathlib import Path


class CMakeExtension(Extension):
    def __init__(self, name):
        super().__init__(name, sources=[])


class CMakeBuild(build_ext):
    def run(self):
        for ext in self.extensions:
            self.build_cmake(ext)
        # Don't call super().run() - we've already built the extension!

    def build_cmake(self, ext):
        # CMake build is handled by CI
        # This just copies the pre-built binary to the right location
        
        # Find the built binary
        executable_dir = Path(__file__).parent / "Executable"
        
        # Platform-specific binary names
        if sys.platform == "win32":
            binary_name = "gp_autointerpolate.pyd"
        elif sys.platform == "darwin":
            binary_name = "gp_autointerpolate.so"
        else:  # Linux
            binary_name = "gp_autointerpolate.so"
        
        # Look for the binary in common build directories
        possible_locations = [
            executable_dir / "output" / "Release" / binary_name,
            executable_dir / "build" / "Release" / binary_name,
            executable_dir / "build" / binary_name,
            executable_dir / "output" / binary_name,  # Added for macOS/Linux
        ]
        
        # Also search recursively as a fallback
        source_binary = None
        for location in possible_locations:
            if location.exists():
                source_binary = location
                print(f"Found binary at: {location}")
                break
        
        # If not found, search recursively
        if source_binary is None:
            print(f"Searching for {binary_name} recursively in {executable_dir}")
            for path in executable_dir.rglob(binary_name):
                source_binary = path
                print(f"Found binary at: {path}")
                break
        
        if source_binary is None:
            # Print directory structure for debugging
            print("Directory structure:")
            for path in executable_dir.rglob("*"):
                if path.is_file():
                    print(f"  {path.relative_to(executable_dir)}")
            raise RuntimeError(f"Could not find built binary: {binary_name}")
        
        # Copy to package location with standard name (no version suffix)
        ext_dir = Path(self.get_ext_fullpath(ext.name)).parent
        ext_dir.mkdir(parents=True, exist_ok=True)
        
        dest_binary = ext_dir / binary_name
        
        print(f"Copying {source_binary} to {dest_binary}")
        shutil.copy(source_binary, dest_binary)


def get_version():
    manifest_path = Path(__file__).parent / "Addon" / "blender_manifest.toml"
    import re
    if manifest_path.exists():
        content = manifest_path.read_text(encoding="utf-8")
        if match := re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE):
            return match.group(1)
    return "2.3.0"  # Fallback

setup(
    name="gp_autointerpolate",
    version=get_version(),
    description="High-performance C++ interpolation module for Blender Grease Pencil",
    author="cosmosmythos",
    url="https://cosmosmythos.gumroad.com/",
    ext_modules=[CMakeExtension("gp_autointerpolate")],  # No version suffix
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
    python_requires=">=3.11",
)
