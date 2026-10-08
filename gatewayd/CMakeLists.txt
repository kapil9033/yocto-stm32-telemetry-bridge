cmake_minimum_required(VERSION 3.16)
project(gatewayd
    VERSION 1.0.0
    DESCRIPTION "Industrial Edge Gateway Daemon for Heterogeneous Yocto/FreeRTOS System"
    LANGUAGES C CXX
)

# ------------------------------------------------------------------------------
# 1. C++ Standard & Build Properties
# ------------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Enable export of compile_commands.json for LSP support (VSCode, clangd)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ------------------------------------------------------------------------------
# 2. Compiler Flags & Security Hardening
# ------------------------------------------------------------------------------
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(
        -Wall
        -Wextra
        -Wpedantic
        -Wshadow
        -Wconversion
        -Wnon-virtual-dtor
        -Wold-style-cast
        -O2
    )
endif()

# ------------------------------------------------------------------------------
# 3. System Dependencies
# ------------------------------------------------------------------------------
find_package(Threads REQUIRED)

# ------------------------------------------------------------------------------
# 4. Include Directories & Target Definition
# ------------------------------------------------------------------------------
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

file(GLOB_RECURSE GATEWAYD_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.c"
)

add_executable(${PROJECT_NAME} ${GATEWAYD_SOURCES})

target_link_libraries(${PROJECT_NAME}
    PRIVATE
        Threads::Threads
)

target_include_directories(${PROJECT_NAME}
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

# ------------------------------------------------------------------------------
# 5. POSIX Installation Targets (Crucial for BitBake/Yocto)
# ------------------------------------------------------------------------------
include(GNUInstallDirs)

install(TARGETS ${PROJECT_NAME}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)