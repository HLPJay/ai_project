find_package(Qt6 COMPONENTS Test REQUIRED)

set(CMAKE_AUTOMOC ON)

set(TEST_SOURCES
    test_stitcher.cpp
)

add_executable(test_stitcher ${TEST_SOURCES})
target_link_libraries(test_stitcher PRIVATE
    Qt6::Test
    ${OpenCV_LIBS}
)
