# Git Submodule Version Checker

Check Git submodules for newer SemVer-style tags and reports which submodules can be updated.

It is intended for CI visibility and maintainer review. It does **not** update submodules by itself unless commanded to.

## What it does

For each Git submodule, the script:

1. Reads the currently checked-out submodule revision.
2. Fetches the latest tags from the configured remote.
4. Parses tags that look like Semantic Versioning.
5. Prints a table with newer version (patch, minor, major).
6. If 'update' was provided, try to update the each submodule to suitable candidate

