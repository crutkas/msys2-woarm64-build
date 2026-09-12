"""Compatibility entry point for the installed native crypt consumer."""

from native_msys_consumer import main

if __name__ == "__main__":
    main(default_package="libxcrypt")
