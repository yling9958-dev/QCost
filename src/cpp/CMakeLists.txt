cmake_minimum_required(VERSION 3.20)
project(QMFIndex LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

add_library(qmap_runtime SHARED
    src/geometry.cpp
    src/static_qmap_index.cpp
    src/runtime_c_api.cpp
)
target_include_directories(qmap_runtime PUBLIC include)
set_target_properties(qmap_runtime PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)

add_executable(qmf_query tools/query_index.cpp)
target_link_libraries(qmf_query PRIVATE qmap_runtime)
set_target_properties(qmf_query PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
