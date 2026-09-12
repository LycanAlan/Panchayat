"""A minimal `zip` for Windows, so `agentcore` will deploy from this machine.

WHY THIS EXISTS

`agentcore configure --deployment-type direct_code_deploy` refuses to run
without a `zip` executable on PATH:

    Error: Direct Code Deploy deployment unavailable (zip utility not found)

That check is spurious. It is `shutil.which("zip")` in exactly two places --
`cli/runtime/_configure_impl.py:434` and `operations/runtime/launch.py:1260` --
and **the toolkit never executes a zip binary**. The packaging code in
`utils/runtime/package.py` does `import zipfile` and builds every archive with
Python's standard library. Grepped the whole package: there is no subprocess
call to `zip` anywhere.

So it is an availability check for a dependency that is not used, and it makes
the toolkit's recommended deploy path unreachable on stock Windows, which has
no `zip`. Linux and macOS ship one, which is presumably why it survived.

WHY A REAL IMPLEMENTATION AND NOT AN EMPTY STUB

An empty `zip.cmd` would satisfy `shutil.which` and unblock the deploy today,
and it would be a trap: the day the toolkit does shell out to zip, it would
"succeed" and upload nothing. This is small enough to just do properly, so the
name does not lie about what it does.

Supports the common form: `zip [-r] [-q] archive.zip path [path ...]`, storing
directories recursively with paths relative to the current directory. Flags the
toolkit does not use are accepted and ignored rather than silently changing
behaviour.

Owner: Ali (platform). Delete this the day the upstream check is fixed.
"""
from __future__ import annotations

import os
import sys
import zipfile


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    quiet = "-q" in argv

    if len(args) < 2:
        print("usage: zip [-r] [-q] archive.zip path [path ...]",
              file=sys.stderr)
        return 2

    archive, paths = args[0], args[1:]
    if not archive.lower().endswith(".zip"):
        archive += ".zip"

    written = 0
    # ZIP_DEFLATED to match what package.py builds, so an archive produced here
    # is not subtly different from one the toolkit made itself.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if os.path.isfile(path):
                zf.write(path)
                written += 1
                continue
            for root, _dirs, files in os.walk(path):
                for name in files:
                    full = os.path.join(root, name)
                    # Relative to CWD, which is what `zip -r` records and what
                    # anything unpacking this will expect.
                    zf.write(full, os.path.relpath(full))
                    written += 1

    if not quiet:
        print("  adding: " + str(written) + " entries -> " + archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
