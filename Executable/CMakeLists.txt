cmake_minimum_required(VERSION 3.15)
project(gp_autointerpolate)

set(CMAKE_CXX_STANDARD 17)

# ============================================================================
# ABI3 STABLE ABI OPTION
# ============================================================================
# Enable with: cmake -DENABLE_ABI3=ON
# Produces cp312-abi3 wheel (covers Python 3.12+). Requires Python >= 3.12 to build.
# Disable (default) for cp311 wheel (Python 3.11 only, Blender 4.3).
option(ENABLE_ABI3 "Build with Python Stable ABI (abi3) for Python 3.12+ compat" OFF)

if(ENABLE_ABI3)
    message(STATUS "Building GP Auto Interpolate module (abi3 mode - Python 3.12+ compat)")
else()
    message(STATUS "Building GP Auto Interpolate module (standard mode - Python 3.11+ compat)")
endif()

# ============================================================================
# CROSS-PLATFORM PYTHON DETECTION
# ============================================================================

# Find Python 3.11+ for Blender 4.2+ compatibility
find_package(Python3 3.11 COMPONENTS Interpreter Development REQUIRED)

# Verify Python version
execute_process(
    COMMAND ${Python3_EXECUTABLE} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    OUTPUT_VARIABLE DETECTED_PYTHON_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

message(STATUS "Detected Python version: ${DETECTED_PYTHON_VERSION}")
message(STATUS "Python executable: ${Python3_EXECUTABLE}")
message(STATUS "Python include dirs: ${Python3_INCLUDE_DIRS}")

# Check Python version compatibility
if(Python3_VERSION_MAJOR EQUAL 3 AND (Python3_VERSION_MINOR EQUAL 11 OR Python3_VERSION_MINOR EQUAL 12 OR Python3_VERSION_MINOR EQUAL 13 OR Python3_VERSION_MINOR EQUAL 14))
    message(STATUS "Python ${DETECTED_PYTHON_VERSION} is officially supported.")
else()
    message(WARNING "Python ${DETECTED_PYTHON_VERSION} found. Officially tested versions are 3.11, 3.12, 3.13, 3.14.")
endif()

# ============================================================================
# NANOBIND SETUP
# ============================================================================

# nanobind uses find_package(Python ...) (not Python3) internally.
# Pre-populate the Python variables so it finds the right installation.
set(Python_ROOT_DIR "${Python3_ROOT_DIR}")
set(Python_EXECUTABLE "${Python3_EXECUTABLE}")
if(ENABLE_ABI3)
    find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)
else()
    find_package(Python 3.11 REQUIRED COMPONENTS Interpreter Development.Module)
endif()

# Fetch nanobind
include(FetchContent)
FetchContent_Declare(
    nanobind
    GIT_REPOSITORY https://github.com/wjakob/nanobind.git
    GIT_TAG v2.9.2
)
FetchContent_MakeAvailable(nanobind)

# ============================================================================
# EIGEN3 DEPENDENCY (for stage_two.cpp)
# ============================================================================

find_package(Eigen3 3.3 QUIET)
if(Eigen3_FOUND)
    message(STATUS "Eigen3 found: ${EIGEN3_INCLUDE_DIR}")
    set(FTPSC_USE_EIGEN ON)
else()
    message(STATUS "Eigen3 not found - Stage 2 PCA will use fallback implementation")
    set(FTPSC_USE_EIGEN OFF)
endif()

# ============================================================================
# NANOFLANN DEPENDENCY (header-only, for stage_two.cpp k-NN search)
# ============================================================================

# Fetch nanoflann (header-only library)
FetchContent_Declare(
    nanoflann
    GIT_REPOSITORY https://github.com/jlblancoc/nanoflann.git
    GIT_TAG v1.5.5
)
FetchContent_MakeAvailable(nanoflann)
message(STATUS "nanoflann fetched successfully (header-only)")
set(FTPSC_USE_NANOFLANN ON)

# ============================================================================
# BUILD MODULE
# ============================================================================

# Collect all FTP-SC source files — similarity_transform removed (topology-driven, no shape)
set(FTPSC_SOURCES
    src/interpolate.cpp
    src/bezier_fit.cpp
    src/fuzzy_topology.cpp
    src/greedy_matcher.cpp
    src/stroke_matcher.cpp
    src/stage_one.cpp
    src/stage_two.cpp
)

if(ENABLE_ABI3)
    nanobind_add_module(gp_autointerpolate STABLE_ABI ${FTPSC_SOURCES})
    # Fix nanobind v2.9.2 CMake bug: nanobind_build_library() checks TARGET_NAME
    # for "-abi3" suffix, but the user module target name never has that suffix.
    # On Windows, this causes the .pyd to link python3XX.dll instead of python3.dll.
    if(WIN32 AND TARGET Python::SABIModule)
        target_link_libraries(gp_autointerpolate PUBLIC Python::SABIModule)
    endif()
else()
    nanobind_add_module(gp_autointerpolate ${FTPSC_SOURCES})
endif()

# macOS: force nanobind static library to build as universal binary too.
# Without this, the module (x86_64+arm64) can't link against the nanobind lib (arm64 only).
if(APPLE)
    foreach(_nb_target IN ITEMS nanobind-static nanobind-static-abi3)
        if(TARGET ${_nb_target})
            set_target_properties(${_nb_target} PROPERTIES
                OSX_ARCHITECTURES "x86_64;arm64"
                MACOSX_DEPLOYMENT_TARGET "10.15"
            )
        endif()
    endforeach()
endif()

# Add compile definitions for optional dependencies
if(FTPSC_USE_EIGEN)
    target_compile_definitions(gp_autointerpolate PRIVATE FTPSC_USE_EIGEN)
    target_link_libraries(gp_autointerpolate PRIVATE Eigen3::Eigen)
endif()

if(FTPSC_USE_NANOFLANN)
    target_compile_definitions(gp_autointerpolate PRIVATE FTPSC_USE_NANOFLANN)
    target_include_directories(gp_autointerpolate PRIVATE ${nanoflann_SOURCE_DIR}/include)
endif()

# Enable static linking for Linux cross-distribution compatibility
if(UNIX AND NOT APPLE)
    # Static link standard C++ libraries for universal Linux compatibility
    target_link_libraries(gp_autointerpolate PRIVATE -static-libgcc -static-libstdc++)
    message(STATUS "Enabled static linking for Linux cross-distro compatibility (Ubuntu/Arch/CachyOS/Fedora/etc)")
endif()

# Cross-platform extension suffix
if(WIN32)
    set_target_properties(gp_autointerpolate PROPERTIES SUFFIX ".pyd")
elseif(UNIX AND NOT APPLE)
    set_target_properties(gp_autointerpolate PROPERTIES
        PREFIX ""  # Remove 'lib' prefix
        SUFFIX ".so"
        INSTALL_RPATH "$ORIGIN"
        BUILD_WITH_INSTALL_RPATH ON
    )
else()
    # macOS
    set_target_properties(gp_autointerpolate PROPERTIES SUFFIX ".so")
endif()

# macOS Universal Binary Support (Intel + Apple Silicon)
if(APPLE)
    set_target_properties(gp_autointerpolate PROPERTIES
        OSX_ARCHITECTURES "x86_64;arm64"
        MACOSX_DEPLOYMENT_TARGET "10.15"
    )
    message(STATUS "Building macOS universal binary (x86_64 + arm64)")
endif()

# Ensure output directory exists
file(MAKE_DIRECTORY "${CMAKE_SOURCE_DIR}/output")

# Set output properties
set_target_properties(gp_autointerpolate PROPERTIES 
    OUTPUT_NAME "gp_autointerpolate"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/output"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/output"
)

# ============================================================================
# OPENMP (OPTIONAL)
# ============================================================================

find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    if(UNIX AND NOT APPLE)
        # Try static OpenMP first for maximum Linux compatibility, fallback to dynamic
        include(CheckLibraryExists)
        check_library_exists(gomp omp_get_num_threads "" HAVE_STATIC_GOMP)
        
        if(HAVE_STATIC_GOMP)
            target_link_libraries(gp_autointerpolate PRIVATE -Wl,-Bstatic -lgomp -Wl,-Bdynamic)
            message(STATUS "OpenMP statically linked for maximum Linux compatibility")
        else()
            target_link_libraries(gp_autointerpolate PRIVATE OpenMP::OpenMP_CXX)
            message(STATUS "OpenMP dynamically linked (static not available)")
        endif()
    else()
        target_link_libraries(gp_autointerpolate PRIVATE OpenMP::OpenMP_CXX)
        message(STATUS "OpenMP linked (Windows/macOS)")
    endif()
else()
    message(STATUS "OpenMP not found - building without parallel support")
endif()

# ============================================================================
# BUILD SUMMARY
# ============================================================================

message(STATUS "=== Build Configuration ===")
message(STATUS "Platform: ${CMAKE_SYSTEM_NAME}")
message(STATUS "Python: ${DETECTED_PYTHON_VERSION}")
message(STATUS "Python executable: ${Python3_EXECUTABLE}")
message(STATUS "Stable ABI (abi3): ${ENABLE_ABI3}")
if(WIN32)
    message(STATUS "Output: gp_autointerpolate.pyd")
elseif(APPLE)
    message(STATUS "Output: gp_autointerpolate.so (Universal Binary: x86_64 + arm64)")
else()
    message(STATUS "Output: gp_autointerpolate.so")
endif()
message(STATUS "Output directory: ${CMAKE_SOURCE_DIR}/output")
message(STATUS "============================")
