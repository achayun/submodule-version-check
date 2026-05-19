# GUSTAV - Git Utility for Submodule Tag-Assisted Versioning

`gustav.py` checks Git submodules against semver-like tags and reports newer patch, minor, and major candidates.
It solves a common submodule maintenance problem: knowing whether pinned submodules have newer tagged releases available, without blindly updating them or inspect every dependent repository by hand.
It is intended for CI visibility and maintainer review. It does not update submodules unless run with the `update` command.

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
