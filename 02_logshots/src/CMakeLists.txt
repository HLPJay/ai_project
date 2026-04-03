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
    ui/window_picker.cpp
    ui/region_selector.cpp
    core/capture/scroll_strategy.cpp
    core/capture/web_capture.cpp
    core/capture/capture_runner.cpp
    core/capture/capture_core.cpp
    core/capture/window_capture.cpp
    core/capture/region_capture.cpp
    core/stitcher/overlap_detector.cpp
    core/stitcher/sticky_detector.cpp
    core/stitcher/image_stitcher.cpp
)

set(APP_HEADERS
    app/application.h
    app/config.h
    ui/main_window.h
    ui/tray_manager.h
    ui/window_picker.h
    ui/region_selector.h
    core/capture/i_capture_engine.h
    core/capture/scroll_strategy.h
    core/capture/web_capture.h
    core/capture/capture_runner.h
    core/capture/capture_core.h
    core/capture/window_capture.h
    core/capture/region_capture.h
    core/stitcher/i_stitcher.h
    core/stitcher/overlap_detector.h
    core/stitcher/sticky_detector.h
    core/stitcher/image_stitcher.h
    core/window/i_window_enumerator.h
)

# Platform interface headers
list(APPEND APP_HEADERS
    platform/interface/i_screen_capturer.h
    platform/interface/i_scroll_input.h
)

# Platform-specific sources
if(WIN32)
    list(APPEND APP_SOURCES
        platform/win/win_window_enum.cpp
        platform/win/win_screen_capture.cpp
        platform/win/win_scroll_input.cpp
    )
    list(APPEND APP_HEADERS
        platform/win/win_window_enum.h
        platform/win/win_screen_capture.h
        platform/win/win_scroll_input.h
    )
elseif(APPLE)
    list(APPEND APP_SOURCES
        platform/mac/mac_window_enum.mm
        platform/mac/mac_screen_capture.cpp
        platform/mac/mac_scroll_input.cpp
    )
    list(APPEND APP_HEADERS
        platform/mac/mac_window_enum.h
        platform/mac/mac_screen_capture.h
        platform/mac/mac_scroll_input.h
    )
endif()

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
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# ============================================
# Platform-Specific Libraries
# ============================================
if(WIN32)
    target_link_libraries(LongShot PRIVATE
        user32
        gdi32
        psapi
        dwmapi
    )
elseif(APPLE)
    target_link_libraries(LongShot PRIVATE
        "-framework CoreGraphics"
        "-framework ApplicationServices"
        "-framework AppKit"
        "-framework Foundation"
    )
endif()

# ============================================
# Windows: x64 triplet
# ============================================
if(WIN32)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
endif()
