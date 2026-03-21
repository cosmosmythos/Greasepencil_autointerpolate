import re
from pathlib import Path

# Path to the REAL GitHub Action
github_yml = Path(r"c:\Users\User\Documents\0\Grease Pencil\Github\Extension\gp_autointerpolate\Greasepencil_autointerpolate\.github\workflows\build.yml")

content = github_yml.read_text(encoding="utf-8")

# 1. Add FORCE_NODE24 environment variable globally (around line 12)
if "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" not in content:
    content = content.replace("jobs:\n", "env:\n  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true\n\njobs:\n")

# 2. Update matrices for BOTH jobs
matrix_replace = """    strategy:
      matrix:
        python-version: ['3.11.9', '3.13.9']
        include:"""
content = re.sub(r"    strategy:\s*matrix:\s*include:", matrix_replace, content)

# 3. Update python setup version for BOTH jobs
content = re.sub(r'python-version: "3\.11\.9"', "python-version: ${{ matrix.python-version }}", content)

# 4. Remove abi3 renaming steps in build_interpolate
interpolate_rename = """      - name: Rename wheels with correct platform tags
        shell: bash
        run: |
          cd dist
          for wheel in *.whl; do
            if [[ $wheel =~ (gp_autointerpolate-[0-9]+\.[0-9]+\.[0-9]+)-.*\.whl ]]; then
              base="${BASH_REMATCH[1]}"
              new_name="${base}-cp311-abi3-${{ matrix.wheel_platform }}.whl"
              if [ "$wheel" != "$new_name" ]; then
                mv "$wheel" "$new_name"
              fi
            fi
            # gp_linevector wheels are built by separate workflow
            # (they require OpenCV dependencies)
          done
          echo "Wheels:"
          ls -la"""
content = content.replace(interpolate_rename, "")

# 5. Remove abi3 renaming steps in build_linevector
linevector_rename = """      - name: Rename wheels with correct platform tags (before bundling - except Linux)
        if: runner.os != 'Linux'
        shell: bash
        run: |
          cd dist
          for wheel in *.whl; do
            if [[ $wheel =~ (gp_linevector-[0-9]+\.[0-9]+\.[0-9]+)-.*\.whl ]]; then
              base="${BASH_REMATCH[1]}"
              new_name="${base}-cp311-abi3-${{ matrix.wheel_platform }}.whl"
              if [ "$wheel" != "$new_name" ]; then
                echo "Renaming: $wheel -> $new_name"
                mv "$wheel" "$new_name"
              fi
            fi
          done
          echo "Wheels after renaming:"
          ls -la"""
content = content.replace(linevector_rename, "")

# 6. Update Artifact Names to include Python version
content = re.sub(r"name: (wheel-interpolate-\$\{\{ matrix\.platform \}\})", r"name: \1-${{ matrix.python-version }}", content)
content = re.sub(r"name: (wheel-linevector-\$\{\{ matrix\.platform \}\})", r"name: \1-${{ matrix.python-version }}", content)

# 7. Add Version Extraction in Package job BEFORE Create platform-specific packages
extract_step = """      - name: Extract Version
        id: extract_version
        shell: bash
        run: |
          VERSION=$(grep -E '^version\s*=' Addon/blender_manifest.toml | cut -d'"' -f2)
          echo "addon_version=$VERSION" >> $GITHUB_ENV
          echo "Detected version: $VERSION"

      - name: Create platform-specific packages"""
content = content.replace("      - name: Create platform-specific packages", extract_step)

# 8. Modernize packaging loop replacing manual cat >> blender_manifest.toml with generate_manifest, and using ${{ env.addon_version }}
# This replaces everything inside the `run:` block of `Create platform-specific packages`
new_package_run = """        run: |
          # Helper function for dynamic manifest generation
          generate_manifest() {
            local _platform=$1
            local _dir=$2
            echo '' >> "$_dir/blender_manifest.toml"
            echo '# BEGIN GENERATED CONTENT.' >> "$_dir/blender_manifest.toml"
            echo '[build.generated]' >> "$_dir/blender_manifest.toml"
            echo "platforms = [\\"$_platform\\"]" >> "$_dir/blender_manifest.toml"
            echo 'wheels = [' >> "$_dir/blender_manifest.toml"
            local _first=true
            for w in "$_dir/wheels/"*.whl; do
              if [ "$_first" = true ]; then
                _first=false
              else
                echo ',' >> "$_dir/blender_manifest.toml"
              fi
              echo -n "  \\"./wheels/$(basename "$w")\\"" >> "$_dir/blender_manifest.toml"
            done
            echo '' >> "$_dir/blender_manifest.toml"
            echo ']' >> "$_dir/blender_manifest.toml"
            echo '# END GENERATED CONTENT.' >> "$_dir/blender_manifest.toml"
          }
          
          # Windows
          echo "Creating Windows package..."
          mkdir -p build_windows/Addon
          cp -r Addon/* build_windows/Addon/
          rm -rf build_windows/Addon/wheels
          mkdir -p build_windows/Addon/wheels
          find wheels-temp -name "*win_amd64.whl" -exec cp {} build_windows/Addon/wheels/ \\;
          
          generate_manifest "windows-x64" "build_windows/Addon"
          cd build_windows/Addon
          zip -r ../../gp_auto_interpolate-${{ env.addon_version }}-windows-x64.zip . -x "*.pyc" -x "__pycache__/*" -x ".DS_Store"
          cd ../..
          
          # macOS Universal (ARM64 + x86_64)
          echo "Creating macOS universal package..."
          mkdir -p build_macos/Addon
          cp -r Addon/* build_macos/Addon/
          rm -rf build_macos/Addon/wheels
          mkdir -p build_macos/Addon/wheels
          find wheels-temp -name "*universal2.whl" -exec cp {} build_macos/Addon/wheels/ \\;
          
          generate_manifest "macos-arm64\\", \\"macos-x64" "build_macos/Addon"
          cd build_macos/Addon
          zip -r ../../gp_auto_interpolate-${{ env.addon_version }}-macos-universal.zip . -x "*.pyc" -x "__pycache__/*" -x ".DS_Store"
          cd ../..
          
          # Linux
          echo "Creating Linux package..."
          mkdir -p build_linux/Addon
          cp -r Addon/* build_linux/Addon/
          rm -rf build_linux/Addon/wheels
          mkdir -p build_linux/Addon/wheels
          find wheels-temp -name "*manylinux*.whl" -exec cp {} build_linux/Addon/wheels/ \\;
          
          generate_manifest "linux-x64" "build_linux/Addon"
          cd build_linux/Addon
          zip -r ../../gp_auto_interpolate-${{ env.addon_version }}-linux-x64.zip . -x "*.pyc" -x "__pycache__/*" -x ".DS_Store"
          cd ../..
          
          echo "✅ Platform-specific packages created:"
          ls -lh gp_auto_interpolate-*.zip"""

# Remove everything from `# Windows` down to just before `      - name: Create Release`
content = re.sub(r'        run: \|\s*# Windows.*?(?=      - name: Create Release)', new_package_run + '\n\n', content, flags=re.DOTALL)

# 9. In the Create Release step, replace 2.3.0 with ${{ env.addon_version }}
content = re.sub(r"2\.3\.0", "${{ env.addon_version }}", content)

github_yml.write_text(content, encoding="utf-8")
print("Fix applied successfully to real github workflow!")
