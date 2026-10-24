cmake_minimum_required(VERSION 3.20)
project(hack_effect_cpp_engine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
    add_compile_options(/W4 /EHsc /utf-8 /MP /permissive-)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS WIN32_LEAN_AND_MEAN NOMINMAX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(hack_effect_core STATIC
    src/param_registry.cpp
    src/metrics.cpp
    src/dsp_blocks.cpp
    src/asio_driver.cpp
    src/audio_host.cpp
    src/ws_server.cpp
)

target_include_directories(hack_effect_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if(WIN32)
    target_link_libraries(hack_effect_core PUBLIC
        ws2_32
        bcrypt
        ole32
        avrt
        mmdevapi
        ksuser
    )
else()
    find_package(Threads REQUIRED)
    target_link_libraries(hack_effect_core PUBLIC Threads::Threads)
endif()

add_executable(hack_effect_host
    src/main.cpp
)
target_link_libraries(hack_effect_host PRIVATE hack_effect_core)

enable_testing()
add_executable(hack_effect_tests
    tests/test_phase1.cpp
)
target_link_libraries(hack_effect_tests PRIVATE hack_effect_core)
add_test(NAME Phase1UnitAndIpcTests COMMAND hack_effect_tests)
