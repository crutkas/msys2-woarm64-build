function(zstd_add_alias alias target dependency result_variable)
    if(NOT alias MATCHES "^[A-Za-z0-9_.-]+$" OR alias STREQUAL target)
        message(FATAL_ERROR "Zstd aliases must be distinct local filenames")
    endif()
    set(alias_file "${alias}")
    set(method create_symlink)
    set(remove_command)
    if(CMAKE_HOST_WIN32)
        set(method create_hardlink)
        if(target STREQUAL "zstd")
            set(target "zstd${CMAKE_EXECUTABLE_SUFFIX}")
            set(alias_file "${alias}${CMAKE_EXECUTABLE_SUFFIX}")
        endif()
        list(APPEND remove_command COMMAND "${CMAKE_COMMAND}" -E rm -f "${CMAKE_CURRENT_BINARY_DIR}/${alias_file}")
    endif()
    add_custom_target("${alias}" ALL
        ${remove_command}
        COMMAND "${CMAKE_COMMAND}" -E "${method}" "${target}" "${alias_file}"
        DEPENDS "${dependency}"
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
        COMMENT "Creating ${alias_file} ${method}"
        VERBATIM)
    set("${result_variable}" "${CMAKE_CURRENT_BINARY_DIR}/${alias_file}" PARENT_SCOPE)
endfunction()
