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
        # Code is in Vectorize/ subdirectory (multi-module project structure)
        vectorize_dir = Path(__file__).parent / "Vectorize"
        print(f"Looking for binary in: {vectorize_dir}")
        
        # Platform-specific binary names
        if sys.platform == "win32":
            binary_name = "gp_linevector.pyd"
        else:
            binary_name = "gp_linevector.so"
        
        # Look for the binary in common build directories
        # Order matches actual build output locations
        possible_locations = [
            vectorize_dir / "output" / "Release" / binary_name,  # Windows MSVC Release build
            vectorize_dir / "output" / binary_name,  # Linux/macOS single-config build
            vectorize_dir / "build" / "Release" / binary_name,   # Alternative MSVC location
            vectorize_dir / "build" / binary_name,               # Alternative single-config location
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
            print(f"\nERROR: Could not find built binary: {binary_name}")
            print(f"\nSearched in these locations:")
            for loc in possible_locations:
                exists = "EXISTS" if loc.exists() else "NOT FOUND"
                print(f"  - {loc} [{exists}]")
            
            print(f"\nAll .pyd/.so files in {vectorize_dir}:")
            found_any = False
            for path in vectorize_dir.rglob("*.pyd"):
                print(f"  {path.relative_to(vectorize_dir)}")
                found_any = True
            for path in vectorize_dir.rglob("*.so"):
                print(f"  {path.relative_to(vectorize_dir)}")
                found_any = True
            if not found_any:
                print("  (none found)")
            
            print(f"\nAll files in output directory:")
            output_dir = vectorize_dir / "output"
            if output_dir.exists():
                for path in output_dir.rglob("*"):
                    if path.is_file():
                        print(f"  {path.relative_to(vectorize_dir)}")
            else:
                print("  output/ directory does not exist")
            
            print(f"\nAll files in build directory:")
            build_dir = vectorize_dir / "build"
            if build_dir.exists():
                for path in build_dir.rglob("*"):
                    if path.is_file() and (path.suffix in ['.pyd', '.so', '.dll', '.lib', '.pdb', '.exp']):
                        print(f"  {path.relative_to(vectorize_dir)}")
            else:
                print("  build/ directory does not exist")
            
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
    return "1.0.0"  # Fallback

setup(
    name="gp_linevector",
    version=get_version(),
    description="High-performance line art vectorization for Blender Grease Pencil",
    author="cosmosmythos",
    url="https://cosmosmythos.gumroad.com/",
    ext_modules=[CMakeExtension("gp_linevector")],  # No version suffix
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
    python_requires=">=3.11",
)
