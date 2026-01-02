"""
Setup script for building gp_linevector wheel
PolyVector field-based line art vectorization module
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
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
        vectorize_dir = Path(__file__).parent / "Vectorize"
        
        # Platform-specific binary names
        if sys.platform == "win32":
            binary_name = "gp_linevector.pyd"
        else:
            binary_name = "gp_linevector.so"
        
        # Look for the binary in common build directories
        possible_locations = [
            vectorize_dir / "output" / "Release" / binary_name,
            vectorize_dir / "build" / "Release" / binary_name,
            vectorize_dir / "build" / binary_name,
            vectorize_dir / "output" / binary_name,  # Added for macOS/Linux
        ]
        
        # Also search recursively as a fallback
        source_binary = None
        for location in possible_locations:
            if location.exists():
                source_binary = location
                print(f"Found binary at: {location}")
                break
        
        # If not found, search recursively (also accept version-suffixed extension modules)
        if source_binary is None:
            print(f"Searching for {binary_name} recursively in {vectorize_dir}")
            for path in vectorize_dir.rglob(binary_name):
                source_binary = path
                print(f"Found binary at: {path}")
                break

        # Windows builds sometimes produce a version-tagged .pyd (e.g. gp_linevector.cp311-win_amd64.pyd)
        if source_binary is None and sys.platform == "win32":
            print(f"Searching for gp_linevector*.pyd recursively in {vectorize_dir}")
            for path in vectorize_dir.rglob("gp_linevector*.pyd"):
                source_binary = path
                print(f"Found binary at: {path}")
                break

        # Linux builds might produce ABI-tagged .so (e.g. gp_linevector.cpython-311-x86_64-linux-gnu.so)
        if source_binary is None and sys.platform != "win32":
            print(f"Searching for gp_linevector*.so recursively in {vectorize_dir}")
            for path in vectorize_dir.rglob("gp_linevector*.so"):
                source_binary = path
                print(f"Found binary at: {path}")
                break
        
        if source_binary is None:
            # Print directory structure for debugging
            print("Directory structure:")
            for path in vectorize_dir.rglob("*"):
                if path.is_file():
                    print(f"  {path.relative_to(vectorize_dir)}")
            raise RuntimeError(f"Could not find built binary: {binary_name}")
        
        # Copy to package location with standard name (no version suffix)
        ext_dir = Path(self.get_ext_fullpath(ext.name)).parent
        ext_dir.mkdir(parents=True, exist_ok=True)
        
        dest_binary = ext_dir / binary_name
        
        print(f"Copying {source_binary} to {dest_binary}")
        shutil.copy(source_binary, dest_binary)


setup(
    name="gp_linevector",
    version="1.0.0",
    description="High-performance line art vectorization for Blender Grease Pencil",
    author="cosmosmythos",
    url="https://cosmosmythos.gumroad.com/",
    ext_modules=[CMakeExtension("gp_linevector")],  # No version suffix
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
    python_requires=">=3.11",
    # Use limited API for Python 3.11+
    options={
        "bdist_wheel": {
            "py_limited_api": "cp311",
        }
    },
)
