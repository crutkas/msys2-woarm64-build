#!/bin/bash

activate_qualified_native_rust() {
    local rust gcc linker_dir unwind
    if [[ ! ${WOARM64_RUST_EPOCH:-} =~ ^[0-9a-f]{64}$ ||
          ! ${WOARM64_TOOLCHAIN_EPOCH:-} =~ ^[0-9a-f]{64}$ ||
          -z ${WOARM64_RUST_PREFIX:-} || -z ${WOARM64_NATIVE_PREFIX:-} ]]; then
        printf 'Native Rust activation requires separately verified Rust and GCC inputs.\n' >&2
        return 1
    fi
    rust=$(cygpath -u "$WOARM64_RUST_PREFIX") || return
    gcc=$(cygpath -u "$WOARM64_NATIVE_PREFIX") || return
    linker_dir=$(cygpath -m "$rust/lib/rustlib/aarch64-pc-windows-gnullvm/bin/gcc-ld") || return
    unwind=$(cygpath -m "$rust/lib/rustlib/aarch64-pc-windows-gnullvm/lib/self-contained/libunwind.dll.a") || return
    export CARGO_TARGET_AARCH64_PC_WINDOWS_GNULLVM_LINKER
    CARGO_TARGET_AARCH64_PC_WINDOWS_GNULLVM_LINKER=$(cygpath -m "$rust/lib/rustlib/aarch64-pc-windows-gnullvm/bin/rust-lld.exe") || return
    export RUSTC RUSTDOC
    RUSTC=$(cygpath -m "$rust/bin/rustc.exe") || return
    RUSTDOC=$(cygpath -m "$rust/bin/rustdoc.exe") || return
    unset RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER
    if [[ ${WOARM64_RUST_FLAGS_APPLIED:-0} != 1 ]]; then
        if [[ ${RUSTFLAGS:-} == *linker-flavor* || ${RUSTFLAGS:-} == *link-self-contained* ||
              ${RUSTFLAGS:-} == *link-arg* || ${RUSTFLAGS:-} == *linker=* ]]; then
            printf 'Conflicting Rust linker flags are not an admitted bridge configuration.\n' >&2
            return 1
        fi
        export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }-C linker-flavor=ld.lld -C link-self-contained=yes -C link-arg=-m -C link-arg=arm64pe"
        export WOARM64_RUST_FLAGS_APPLIED=1
    fi
    export PATH="$gcc/bin:$rust/bin:$PATH"
    if declare -F check_buildoption >/dev/null && check_buildoption ccache y; then
        export PATH="/usr/lib/ccache/bin:$PATH"
    fi
    printf -v WOARM64_RUST_LDFLAGS ' -B%q -fuse-ld=lld -Wl,-m,arm64pe' "$linker_dir"
    printf -v WOARM64_RUST_EXTLIBS ' -lkernel32 -lntdll -luserenv -lws2_32 -ldbghelp %q' "$unwind"
    export WOARM64_RUST_LDFLAGS WOARM64_RUST_EXTLIBS
}

activate_qualified_native_rust
