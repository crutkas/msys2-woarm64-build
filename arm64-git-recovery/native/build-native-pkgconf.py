"""Compatibility entry point for the native pkgconf Meson recipe."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("build-native-meson.py")), run_name="__main__")
