cmake_minimum_required(VERSION 3.20)
project(LongShot VERSION 1.0.0 LANGUAGES CXX)

# ============================================
# Build Options
# ============================================
option(BUILD_TESTS "Build unit tests" ON)

# ============================================
# C++ Standard
# ============================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ============================================
# Compiler Flags
# ============================================
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Werror)
endif()

# ============================================
# Find Qt6
# ============================================
find_package(Qt6 COMPONENTS Widgets Gui Core REQUIRED)

# ============================================
# Find OpenCV
# ============================================
find_package(OpenCV REQUIRED)

# ============================================
# Source Directory
# ============================================
add_subdirectory(src)

# ============================================
# Tests
# ============================================
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
