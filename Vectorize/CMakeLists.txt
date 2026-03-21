cmake_minimum_required(VERSION 3.15)
project(gp_linevector)

set(CMAKE_CXX_STANDARD 17)

message(STATUS "Building GP LineVector module for Blender 4.3+")
message(STATUS "Stable ABI (abi3) build - compatible with Python 3.11+ (Blender 4.3 to 5.x and beyond)")
message(STATUS "PolyVector-based line art vectorization")

# ============================================================================
# CROSS-PLATFORM PYTHON DETECTION (same as interpolate.cpp)
# ============================================================================

# Find Python 3.11+ - minimum version for abi3 target
# abi3 means this binary works on Python 3.11, 3.12, 3.13, 3.14... forever
# NOTE: We intentionally do NOT use the EXACT keyword here.
# "find_package(Python3 3.11 EXACT)" with only two version components does NOT
# reliably enforce an exact minor version - CMake may still find 3.12+.
# Python version is pinned by CI (setup-python: 3.11.9) - that is the real guard.
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

# NOTE: PYBIND11_FINDPYTHON OFF has been removed.
# It was originally added to stop pybind11 grabbing the wrong Python on
# multi-version local machines. However, setting it OFF activates pybind11's
# legacy cmake tools which do NOT understand the STABLE_ABI keyword, causing
# a build failure ("Cannot find source file: STABLE_ABI").
# In CI, setup-python ensures only 3.11.9 exists - no ambiguity.
# Locally, find_package(Python3 3.11) above already found the right one first.

# ============================================================================
# PYBIND11 SETUP
# ============================================================================

include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v3.0.1
)
FetchContent_MakeAvailable(pybind11)

# ============================================================================
# OPENCV (REQUIRED)
# ============================================================================

find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs)
message(STATUS "OpenCV ${OpenCV_VERSION} found")
message(STATUS "OpenCV libraries: ${OpenCV_LIBS}")

# ============================================================================
# EIGEN3 (REQUIRED - Header-only)
# ============================================================================

find_package(Eigen3 REQUIRED)
message(STATUS "Eigen3 found")

# ============================================================================
# BOOST (REQUIRED - Header-only Graph Library)
# ============================================================================

find_package(Boost 1.48 REQUIRED)
message(STATUS "Boost ${Boost_VERSION} found")

# ============================================================================
# COLLECT SOURCE FILES
# ============================================================================

file(GLOB POLYVECTOR_SOURCES "src_polyvector/*.cpp")
list(REMOVE_ITEM POLYVECTOR_SOURCES 
    "${CMAKE_CURRENT_SOURCE_DIR}/src_polyvector/polyvector_pybind.cpp"
)

# Debug: Show what files are being compiled
message(STATUS "=== PolyVector Source Files ===")
foreach(src_file ${POLYVECTOR_SOURCES})
    get_filename_component(filename ${src_file} NAME)
    message(STATUS "  - ${filename}")
endforeach()
message(STATUS "Total: ${CMAKE_CURRENT_LIST_LENGTH} files (excluding pybind wrapper)")

# ============================================================================
# BUILD MODULE
# ============================================================================

# STABLE_ABI: compile once, works on Python 3.11, 3.12, 3.13, 3.14... forever
pybind11_add_module(gp_linevector STABLE_ABI
    src_polyvector/polyvector_pybind.cpp
    ${POLYVECTOR_SOURCES}
)
target_compile_definitions(gp_linevector PRIVATE Py_LIMITED_API=0x030B0000)

# Link libraries
target_link_libraries(gp_linevector PRIVATE 
    ${OpenCV_LIBS}
    Eigen3::Eigen
)

target_include_directories(gp_linevector PRIVATE
    ${Boost_INCLUDE_DIRS}
    ${OpenCV_INCLUDE_DIRS}
    src_polyvector
    src_polyvector/LBFGS
)

# ============================================================================
# CROSS-PLATFORM SETTINGS (same as interpolate.cpp)
# ============================================================================

# Enable static linking for Linux cross-distribution compatibility
if(UNIX AND NOT APPLE)
    # Static link standard C++ libraries for universal Linux compatibility
    target_link_libraries(gp_linevector PRIVATE -static-libgcc -static-libstdc++)
    message(STATUS "Enabled static linking for Linux cross-distro compatibility")
endif()

# Cross-platform extension suffix
if(WIN32)
    set_target_properties(gp_linevector PROPERTIES SUFFIX ".pyd")
elseif(UNIX AND NOT APPLE)
    set_target_properties(gp_linevector PROPERTIES
        PREFIX ""  # Remove 'lib' prefix
        SUFFIX ".so"
        INSTALL_RPATH "$ORIGIN"
        BUILD_WITH_INSTALL_RPATH ON
    )
else()
    # macOS
    set_target_properties(gp_linevector PROPERTIES SUFFIX ".so")
endif()

# macOS Architecture Support
if(APPLE)
    # Respect CMAKE_OSX_ARCHITECTURES if set by workflow
    # Otherwise default to universal binary for local builds
    if(NOT DEFINED CMAKE_OSX_ARCHITECTURES OR CMAKE_OSX_ARCHITECTURES STREQUAL "")
        set_target_properties(gp_linevector PROPERTIES
            OSX_ARCHITECTURES "x86_64;arm64"
        )
        message(STATUS "Building macOS universal binary (x86_64 + arm64)")
    else()
        set_target_properties(gp_linevector PROPERTIES
            OSX_ARCHITECTURES "${CMAKE_OSX_ARCHITECTURES}"
        )
        message(STATUS "Building macOS for architecture: ${CMAKE_OSX_ARCHITECTURES}")
    endif()
    
    set_target_properties(gp_linevector PROPERTIES
        MACOSX_DEPLOYMENT_TARGET "10.15"
    )
endif()

# Ensure output directory exists
file(MAKE_DIRECTORY "${CMAKE_SOURCE_DIR}/output")

# Set output properties
# On Windows MSVC, explicitly set output for all configurations to avoid Release/Debug subdirs
if(MSVC)
    foreach(config ${CMAKE_CONFIGURATION_TYPES})
        string(TOUPPER ${config} config_upper)
        set_target_properties(gp_linevector PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY_${config_upper} "${CMAKE_SOURCE_DIR}/output"
            RUNTIME_OUTPUT_DIRECTORY_${config_upper} "${CMAKE_SOURCE_DIR}/output"
        )
    endforeach()
endif()

set_target_properties(gp_linevector PROPERTIES 
    OUTPUT_NAME "gp_linevector"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/output"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/output"
)

# ============================================================================
# COMPILER OPTIMIZATION FLAGS
# ============================================================================

# Enable maximum optimization for production builds
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(APPLE)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3")
    else()
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3")
    endif()
    message(STATUS "Compiler flags (GCC/Clang): ${CMAKE_CXX_FLAGS}")
    # Optional: Enable fast math (trades precision for speed)
    # Uncomment if you need maximum performance and can tolerate minor FP differences
    # set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -ffast-math")
elseif(MSVC)
    # Using /fp:precise for better numerical accuracy
    # /arch:AVX2 removed - improves compatibility across older CPUs (pre-2013 hardware)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /O2 /fp:precise")
    message(STATUS "Compiler flags (MSVC): ${CMAKE_CXX_FLAGS}")
endif()

# ============================================================================
# OPENMP (OPTIONAL)
# ============================================================================

find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    if(UNIX AND NOT APPLE)
        include(CheckLibraryExists)
        check_library_exists(gomp omp_get_num_threads "" HAVE_STATIC_GOMP)
        if(HAVE_STATIC_GOMP)
            target_link_libraries(gp_linevector PRIVATE -Wl,-Bstatic -lgomp -Wl,-Bdynamic)
            message(STATUS "OpenMP statically linked for maximum Linux compatibility")
        else()
            target_link_libraries(gp_linevector PRIVATE OpenMP::OpenMP_CXX)
            message(STATUS "OpenMP dynamically linked (static not available)")
        endif()
    else()
        target_link_libraries(gp_linevector PRIVATE OpenMP::OpenMP_CXX)
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
message(STATUS "OpenCV: ${OpenCV_VERSION}")
message(STATUS "Boost: ${Boost_VERSION}")
message(STATUS "ABI: Stable ABI (abi3) - works on Python 3.11+")
if(WIN32)
    message(STATUS "Output: gp_linevector.pyd")
elseif(APPLE)
    message(STATUS "Output: gp_linevector.so (Universal Binary: x86_64 + arm64)")
else()
    message(STATUS "Output: gp_linevector.so")
endif()
message(STATUS "Output directory: ${CMAKE_SOURCE_DIR}/output")
message(STATUS "Compatible with: Blender 4.3+ (all future versions)")
message(STATUS "===========================")
