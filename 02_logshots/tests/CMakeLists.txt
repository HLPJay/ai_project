find_package(Qt6 COMPONENTS Test Gui REQUIRED)

set(CMAKE_AUTOMOC ON)

set(TEST_SOURCES
    test_overlap_detector.cpp
    ${CMAKE_SOURCE_DIR}/src/core/stitcher/overlap_detector.cpp
    ${CMAKE_SOURCE_DIR}/src/core/stitcher/sticky_detector.cpp
)

add_executable(test_stitcher ${TEST_SOURCES})
target_include_directories(test_stitcher PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)
target_link_libraries(test_stitcher PRIVATE
    Qt6::Test
    Qt6::Core
    Qt6::Gui
    ${OpenCV_LIBS}
)

# Window Enumerator Tests
if(WIN32)
    set(WINDOW_ENUM_SOURCES
        test_window_enumerator.cpp
        ${CMAKE_SOURCE_DIR}/src/platform/win/win_window_enum.cpp
        ${CMAKE_SOURCE_DIR}/src/core/window/i_window_enumerator.cpp
    )
elseif(APPLE)
    set(WINDOW_ENUM_SOURCES
        test_window_enumerator.cpp
        ${CMAKE_SOURCE_DIR}/src/platform/mac/mac_window_enum.mm
        ${CMAKE_SOURCE_DIR}/src/platform/mac/mac_window_enum.h
    )
else()
    # No window enumerator for other platforms
    set(WINDOW_ENUM_SOURCES "")
endif()

if(WINDOW_ENUM_SOURCES)
    add_executable(test_window_enumerator ${WINDOW_ENUM_SOURCES})
    target_include_directories(test_window_enumerator PRIVATE
        ${CMAKE_SOURCE_DIR}/src
    )

    if(WIN32)
        target_link_libraries(test_window_enumerator PRIVATE
            Qt6::Test
            Qt6::Core
            Qt6::Gui
            user32
            gdi32
            psapi
        )
    elseif(APPLE)
        target_link_libraries(test_window_enumerator PRIVATE
            Qt6::Test
            Qt6::Core
            Qt6::Gui
            "-framework CoreGraphics"
            "-framework AppKit"
            "-framework Foundation"
        )
    endif()
endif()

# Window Picker Tests
if(WIN32)
    set(WINDOW_PICKER_SOURCES
        test_window_picker.cpp
        ${CMAKE_SOURCE_DIR}/src/ui/window_picker.cpp
        ${CMAKE_SOURCE_DIR}/src/core/window/i_window_enumerator.cpp
    )
elseif(APPLE)
    set(WINDOW_PICKER_SOURCES
        test_window_picker.cpp
        ${CMAKE_SOURCE_DIR}/src/ui/window_picker.cpp
        ${CMAKE_SOURCE_DIR}/src/core/window/i_window_enumerator.cpp
    )
else()
    set(WINDOW_PICKER_SOURCES "")
endif()

if(WINDOW_PICKER_SOURCES)
    add_executable(test_window_picker ${WINDOW_PICKER_SOURCES})
    target_include_directories(test_window_picker PRIVATE
        ${CMAKE_SOURCE_DIR}/src
    )

    if(WIN32)
        target_link_libraries(test_window_picker PRIVATE
            Qt6::Test
            Qt6::Core
            Qt6::Gui
            Qt6::Widgets
            user32
            gdi32
            psapi
        )
    elseif(APPLE)
        target_link_libraries(test_window_picker PRIVATE
            Qt6::Test
            Qt6::Core
            Qt6::Gui
            Qt6::Widgets
            "-framework CoreGraphics"
            "-framework AppKit"
            "-framework Foundation"
        )
    endif()
endif()
