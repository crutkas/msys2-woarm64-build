import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt" and os.environ.get("NATIVE_TEST_CMAKE") and os.environ.get("NATIVE_TEST_NINJA"),
                     "Existing native Windows CMake/Ninja are required")
class ZstdAliasControls(unittest.TestCase):
    def test_real_hardlinks_refresh_and_install_with_executable_names(self):
        scripts = Path(__file__).parent.resolve()
        cmake, ninja = os.environ["NATIVE_TEST_CMAKE"], os.environ["NATIVE_TEST_NINJA"]
        with tempfile.TemporaryDirectory(prefix="zstd alias control ") as temporary:
            root = Path(temporary)
            build, stage = root / "build", root / "stage"

            def run(*args):
                result = subprocess.run([cmake, *map(str, args)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            run("-S", scripts / "fixtures/zstd-aliases", "-B", build, "-G", "Ninja",
                "-DCMAKE_SYSTEM_NAME=MSYS", f"-DCMAKE_MAKE_PROGRAM={Path(ninja).as_posix()}",
                f"-DALIAS_HELPER={(scripts / 'cmake/ZstdProgramAlias.cmake').as_posix()}",
                f"-DCMAKE_INSTALL_PREFIX={stage.as_posix()}")
            run("--build", build, "--parallel", "1")
            for name in ("zstdcat", "unzstd", "zstdmt"):
                self.assertTrue(os.path.samefile(build / "zstd.exe", build / f"{name}.exe"))
            for name in ("zstdcat.1", "unzstd.1"):
                self.assertTrue(os.path.samefile(build / "zstd.1", build / name))
            (build / "zstd.exe").unlink()
            (build / "zstd.exe").write_bytes(b"Replacement unexecuted file fixture\n")
            run("--build", build, "--parallel", "1")
            run("--install", build)
            for name in ("zstdcat", "unzstd", "zstdmt"):
                self.assertTrue(os.path.samefile(build / "zstd.exe", build / f"{name}.exe"))
                self.assertEqual((stage / f"bin/{name}.exe").read_bytes(), (build / "zstd.exe").read_bytes())
            for name in ("zstdcat.1", "unzstd.1"):
                self.assertEqual((stage / f"share/man/man1/{name}").read_bytes(), (build / "zstd.1").read_bytes())


if __name__ == "__main__":
    unittest.main()
