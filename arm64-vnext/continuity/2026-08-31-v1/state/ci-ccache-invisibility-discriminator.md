# Discriminator for the ccache/makeinfo invisibility — ready to apply

Settles which of two mechanisms causes `checking for makeinfo... no` (and
`checking for aarch64-w64-mingw32-gcc... no`) despite
`.github/scripts/enable-ccache.sh` creating both symlinks in
`/usr/lib/ccache/bin` without error.

- **(A)** `/usr/lib/ccache/bin` is never prepended to `PATH` in the build env.
- **(B)** the symlinks are created under `export MSYS=winsymlinks`
  (`enable-ccache.sh:39`) — a bare legacy value meaning `.lnk`-style symlinks —
  and are therefore not resolvable as plain executables.

## THE TRAP TO AVOID — do not "just print PATH in the build step"

`makepkg` prepends the ccache directory **internally**, when
`BUILDENV=(... ccache ...)` is set. It does not export it to the job shell.
So `echo $PATH` in the Build step will legitimately **not** contain
`/usr/lib/ccache/bin` **even when ccache is working perfectly**, and reading
that as "PATH is broken" would confirm (A) falsely.

**State this plainly, because "unreliable" is not a strong enough warning to stop
someone running it: the naive `echo $PATH` probe does not merely fail to settle
the question — it FALSELY CONFIRMS (A). It returns a clean, decisive-looking
result that points at the wrong mechanism.** A reader told only that it is "weak"
will run it anyway and act on the answer.

A diagnostic whose negative result is indistinguishable from correct behaviour
is not a diagnostic.

## The decisive test — isolates (B) with no reference to makepkg at all

Add as a step **after** `Enable Ccache` in `.github/workflows/build-package.yml`:

```yaml
      - name: Diagnose ccache bin visibility
        if: always()
        run: |
          probe () {
            d="$1"; n="$2"
            if [ -x "$d/$n" ] && PATH="$d:$PATH" "$n" --version >/dev/null 2>&1; then
              echo "$n: RESOLVABLE+RUNNABLE"
            elif [ -L "$d/$n" ] && [ ! -e "$d/$n" ]; then
              echo "$n: PRESENT-BUT-BROKEN-SYMLINK"
            elif [ -e "$d/$n" ]; then
              echo "$n: PRESENT-BUT-NOT-RUNNABLE"
            else
              echo "$n: ABSENT"
            fi
          }
          echo "--- contents of /usr/lib/ccache/bin ---"
          ls -la /usr/lib/ccache/bin/ || echo "DIRECTORY MISSING"
          echo "--- probes with the directory FORCED onto PATH ---"
          probe /usr/lib/ccache/bin makeinfo
          probe /usr/lib/ccache/bin aarch64-w64-mingw32-gcc
```

**Why this is decisive:** it forces the directory onto `PATH` explicitly, so the
only remaining variable is whether the entries are usable executables. It cannot
be confounded by makepkg behaviour, because makepkg is not involved.

Read the result as:

| probe output | mechanism | fix |
|---|---|---|
| `RESOLVABLE+RUNNABLE` | **(A)** — entries are fine, makepkg never prepends the dir | put the stub in a directory already on `PATH` (e.g. `/usr/local/bin`), or fix the ccache PATH injection |
| `PRESENT-BUT-BROKEN-SYMLINK` | **(B)** — `MSYS=winsymlinks` produced an unusable link | `export MSYS=winsymlinks:nativestrict`, or write a real script instead of a symlink |
| `PRESENT-BUT-NOT-RUNNABLE` | **(B)** variant — created without exec permission | `chmod +x`, or write a real script |
| `ABSENT` | the `ln -sf` never took effect at that path, **or** it produced only `makeinfo.lnk` | inspect the `ls -la` output above to tell these apart |

### The probe logic is control-validated (5/5)

Do not simplify it to `command -v`. **`command -v` reports a non-executable
file as resolvable**, which would falsely report mechanism (A). Measured:

| control | probe output | correct |
|---|---|---|
| executable script | `RESOLVABLE+RUNNABLE` | yes |
| file without `+x` | `PRESENT-BUT-NOT-RUNNABLE` | yes |
| empty directory | `ABSENT` | yes |
| dangling symlink | `PRESENT-BUT-BROKEN-SYMLINK` | yes |
| only `makeinfo.lnk` present | `ABSENT` | yes |

The dangling-symlink case is the one that matters most and the one a naive probe
gets wrong: `[ -e ]` follows symlinks, so a broken link tests as *absent*, which
would conflate **"the stub was never created"** with **"the stub was created and
is broken"** — precisely the (A)/(B) distinction this test exists to make.

## Unblock that does not require knowing the answer

The cross chain can be freed independently of (A)/(B), since binutils only needs
the doc build suppressed:

- `MAKEINFO=true` in the cross-binutils PKGBUILD `build()` environment, or
- `--disable-docs` / skip the `info` target in its configure invocation.

This is the lower-risk change if the goal is only to get the cross toolchain
past `doc/bfd.info`. It does **not** fix the inert ccache, which is a separate
cost (every cross job currently builds uncached).

## Scope limits

- Not established which mechanism is true. This document proposes the test, not
  the answer.
- The seven **native** jobs are unaffected by any of the above: they wait on
  `["Windows","ARM64","MSYS2"]` labels and `actions/runners` reports
  `total_count=0`. No repo change can start them.
- The binutils failure predates this work (identical job failing on commits from
  2026-09-01), so neither fix is a regression repair.
