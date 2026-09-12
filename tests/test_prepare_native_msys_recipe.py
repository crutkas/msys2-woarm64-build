import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "prepare-native-msys-recipe.ps1"

RECIPES = {
    "less": (
        "9d443477b3a9ae72d677736d555b523ac947e6305cf1918922f4ad899827b522",
        r"""# Maintainer: Alexey Pavlov <alexpux@gmail.com>

pkgname=less
pkgver=704
pkgrel=1
pkgdesc="A terminal based program for viewing text files"
license=('spdx:GPL-3.0-or-later')
arch=('i686' 'x86_64')
url="http://www.greenwoodsoftware.com/less"
msys2_repository_url="https://github.com/gwsw/less"
msys2_references=(
  "cpe: cpe:/a:gnu:less"
)
depends=('ncurses' 'libpcre2_8')
makedepends=('ncurses-devel' 'pcre2-devel' 'autotools' 'gcc' 'groff')
source=("https://github.com/gwsw/${pkgname}/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('0a801a147af1e41c1d9daa273316ce6d560053534659b5487ed5de6fc5032de4')
validpgpkeys=('AE27252BD6846E7D6EAE1DD6F153A7C833235259') # Mark Nudelman

prepare() {
  cd ${srcdir}/${pkgname}-${pkgver}

  autoreconf -vfi
}

build() {
  cd ${srcdir}/${pkgname}-${pkgver}
  make -f Makefile.aut distfiles

  ./configure \
      --build=${CHOST} \
      --prefix=/usr \
      --sysconfdir=/etc \
      --with-regex=pcre2
  make
}

package() {
  cd ${srcdir}/${pkgname}-${pkgver}
  make DESTDIR=${pkgdir} install
}
""",
    ),
    "pcre2": (
        "df23b70c3950ef49b010a1fdf0ea010211e5d1365c0c10eb0ce6f32153f241a3",
        None,
    ),
}


class PrepareNativeMsysRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("pwsh") is None:
            raise unittest.SkipTest("PowerShell 7 is required")

    def run_script(self, package, source, output):
        return subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(SCRIPT),
                "-Package",
                package,
                "-SourceRecipe",
                str(source),
                "-OutputRecipe",
                str(output),
            ],
            capture_output=True,
            text=True,
        )

    def test_less_changes_only_architecture(self):
        expected_hash, recipe = RECIPES["less"]
        self.assertEqual(hashlib.sha256(recipe.encode()).hexdigest(), expected_hash)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PKGBUILD"
            output = root / "prepared" / "PKGBUILD"
            source.write_text(recipe, encoding="utf-8", newline="\n")
            result = self.run_script("less", source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            prepared = output.read_text(encoding="utf-8")
            self.assertEqual(
                prepared.replace("arch=('aarch64')", "arch=('i686' 'x86_64')"),
                recipe,
            )
            receipt = json.loads(Path(f"{output}.preparation.json").read_text())
            self.assertEqual(receipt["status"], "native-msys-recipe-prepared-not-built")
            self.assertEqual(receipt["package"], "less")
            self.assertIn("--with-regex=pcre2", prepared)

    def test_rejects_unpinned_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PKGBUILD"
            source.write_text("arch=('i686' 'x86_64')\n", encoding="utf-8")
            result = self.run_script("less", source, root / "out")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unexpected pinned less recipe hash", result.stderr)

    def test_rejects_existing_output(self):
        _, recipe = RECIPES["less"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PKGBUILD"
            output = root / "out"
            source.write_text(recipe, encoding="utf-8", newline="\n")
            output.write_text("existing", encoding="ascii")
            result = self.run_script("less", source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Prepared recipe output must be new", result.stderr)


if __name__ == "__main__":
    unittest.main()
