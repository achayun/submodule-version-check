# GUSTAV - Git Utility for Submodule Tag-Assisted Versioning

`gustav.py` checks Git submodules against semver-like tags and reports newer patch, minor, and major candidates.
It solves a common submodule maintenance problem: knowing whether pinned submodules have newer tagged releases available, without blindly updating them or inspect every dependent repository by hand.
It is intended for CI visibility and maintainer review. It does not update submodules unless run with the `update` command.

## Example Output

```
$ gustav.py
Path      Current  Patch   Minor   Major   Branch
libs/foo  v1.0.0   v1.0.1  v1.1.0  v2.0.0  -
libs/bar  v1.0.0   v1.0.1  -       -       -
libs/baz  v1.0.0   v1.0.1  -       -       main

$ gustav.py update --update-policy minor
Path      Current  Patch   Minor   Major   Branch
libs/foo  v1.0.0   v1.0.1  v1.1.0  v2.0.0  -
libs/bar  v1.0.0   v1.0.1  -       -       -
libs/baz  v1.0.0   v1.0.1  -       -       main

Updated 2 modules:
	libs/foo: minor update eb05c5c (v1.0.0) -> 767fc5a (v1.1.0)
	libs/bar: patch update eb05c5c (v1.0.0) -> dc320a7 (v1.0.1)

Skipped 1 module:
	libs/baz: not pinned, following branch main

Commit message saved to <repo>/.git/GUSTAV_COMMIT_MSG
  Edit:     git commit -F <repo>/.git/GUSTAV_COMMIT_MSG -e
  Commit:   git commit -F <repo>/.git/GUSTAV_COMMIT_MSG
```

## What it does

For each Git submodule, `gustav.py`:

1. Reads the currently checked-out revision.
2. Fetches tags from the configured remote.
3. Parses Semantic Version-like tags.
4. Reports newer patch, minor, and major candidates.

## Update behavior

The `--update-policy` option controls which class of available version is selected.

By default, `gustav` uses the conservative `patch` policy. For example, a submodule at `1.1.2` may be updated to `1.1.3`, but not to `1.2.0`.
Policies are inclusive. For example, `minor` allows both patch and minor upgrades, but rejects major upgrades.

Policies define the maximum allowed upgrade class:

- `patch`: select the latest patch release within the current minor series.
- `minor`: select the latest patch or minor release within the current major series.
- `major`: select the latest available release, including major upgrades.

Submodules that are configured to track a branch in .gitmodules are skipped in the update.

## Limitations

`gustav` does not resolve dependency constraints, compatibility rules, release metadata, changelogs, or transitive requirements.

Results depend on repositories using meaningful semver-like tags. Repositories with missing, inconsistent, misleading, or unconventional version tags may produce incomplete or noisy results.

When in doubt, review the selected candidates manually.

`gustav` is not a package manager; Just feed him a spot.
