# ============================================
# Qt Auto-MOC/UIC/RCC
# ============================================
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

# ============================================
# Find Qt6
# ============================================
find_package(Qt6 REQUIRED COMPONENTS Widgets WebEngineWidgets)

# ============================================
# Application Target
# ============================================
set(APP_SOURCES
    main.cpp
    app/application.cpp
    app/config.cpp
    ui/main_window.cpp
    ui/tray_manager.cpp
    core/capture/scroll_strategy.cpp
    core/capture/web_capture.cpp
    core/capture/capture_runner.cpp
    core/capture/capture_core.cpp
)

set(APP_HEADERS
    app/application.h
    app/config.h
    ui/main_window.h
    ui/tray_manager.h
    core/capture/i_capture_engine.h
    core/capture/scroll_strategy.h
    core/capture/web_capture.h
    core/capture/capture_runner.h
    core/capture/capture_core.h
)

add_executable(LongShot
    ${APP_SOURCES}
    ${APP_HEADERS}
)

# ============================================
# Qt6 Link Libraries
# ============================================
target_link_libraries(LongShot PRIVATE
    Qt6::Widgets
    Qt6::Gui
    Qt6::Core
    Qt6::WebEngineWidgets
)

# ============================================
# OpenCV Link Libraries
# ============================================
target_link_libraries(LongShot PRIVATE
    ${OpenCV_LIBS}
)

# ============================================
# Include Directories
# ============================================
target_include_directories(LongShot PRIVATE
    ${OpenCV_INCLUDE_DIRS}
)

# ============================================
# Windows: x64 triplet
# ============================================
if(WIN32)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
endif()
