cmake_minimum_required(VERSION 3.15)
project(gp_autointerpolate)

set(CMAKE_CXX_STANDARD 17)

message(STATUS "Building GP Auto Interpolate module for Blender 4.3+")
message(STATUS "Universal compatibility with Python 3.11.x")

# ============================================================================
# CROSS-PLATFORM PYTHON DETECTION
# ============================================================================

# Find Python 3.11.x for Blender 4.3+ compatibility
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

# Warn if not Python 3.11.x
if(NOT Python3_VERSION_MAJOR EQUAL 3 OR NOT Python3_VERSION_MINOR EQUAL 11)
    message(WARNING "Python ${DETECTED_PYTHON_VERSION} found, but Blender 4.3+ requires Python 3.11.x")
    message(WARNING "This may cause compatibility issues with Blender")
endif()

# Force pybind11 to use our detected Python (your fix!)
set(PYBIND11_FINDPYTHON OFF CACHE BOOL "Disable pybind11 auto Python detection" FORCE)

# ============================================================================
# PYBIND11 SETUP
# ============================================================================

# Fetch pybind11
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v3.0.1
)
FetchContent_MakeAvailable(pybind11)

# Force pybind11 to use our detected Python again (your fix - required twice!)
set(PYBIND11_FINDPYTHON OFF CACHE BOOL "Disable pybind11 auto Python detection" FORCE)

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

# Collect all FTP-SC source files
set(FTPSC_SOURCES
    src/interpolate.cpp
    src/fuzzy_topology.cpp
    src/greedy_matcher.cpp
    src/salient_point_matcher.cpp
    src/similarity_transform.cpp
    src/stroke_matcher.cpp
    src/stage_one.cpp
    src/stage_two.cpp
)

pybind11_add_module(gp_autointerpolate ${FTPSC_SOURCES})

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
if(WIN32)
    message(STATUS "Output: gp_autointerpolate.pyd")
elseif(APPLE)
    message(STATUS "Output: gp_autointerpolate.so (Universal Binary: x86_64 + arm64)")
else()
    message(STATUS "Output: gp_autointerpolate.so")
endif()
message(STATUS "Output directory: ${CMAKE_SOURCE_DIR}/output")
message(STATUS "Compatible with: Blender 4.3+")
message(STATUS "============================")