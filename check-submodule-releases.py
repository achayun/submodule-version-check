import argparse
import configparser
import json
import os
import re
import subprocess
import sys
from typing import NamedTuple

# Regex to break a semver string to a tuple.
# Based on: https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
# Modified to:
# * Accept optional 'v' prefix (e.g. v1.2.3)
# * Case insensitive match
# * Make Patch optional (e.g. 1.2 -> 1.2.0)
SEMVER_RE = re.compile(
    r'^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)(\.(?P<patch>0|[1-9]\d*))?(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-z-]+(?:\.[0-9a-z-]+)*))?$'
, re.IGNORECASE)

class Semver(NamedTuple):
    major: int
    minor: int
    patch: int
    prerelease: str | None
    buildmetadata: str | None
    tag: str    # The original string that was parsed, kept last to maintain tuple ordering


def parse_semver(tag: str) -> Semver | None:
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    return Semver(
        int(m.group('major')),
        int(m.group('minor')),
        int(m.group('patch')) if m.group('patch') else 0,
        m.group('prerelease'),
        m.group('buildmetadata'),
        tag,
    )


def parse_tags_to_semver(tags: list[str]) -> list[Semver]:
    return list(filter(None, map(parse_semver, tags)))


def find_updates(current: Semver | None, versions: list[Semver]) -> list[Semver]:
    if current is None:
        return None, None, max(versions, default=None)
    newer = [v for v in versions if v > current]
    patch = max((v for v in newer if v.major == current.major and v.minor == current.minor), default=None)
    minor = max((v for v in newer if v.major == current.major and v.minor > current.minor), default=None)
    major = max((v for v in newer if v.major > current.major), default=None)
    return patch, minor, major


def parse_gitmodules(root: str) -> dict:
    config = configparser.ConfigParser(interpolation=None, strict=True, empty_lines_in_values=False)
    config.read(os.path.join(root, '.gitmodules'))
    modules = {}
    for section in config.sections():
        if section.startswith('submodule '):
            data = dict(config[section])
            if subpath := data.get('path'):
                modules[subpath] = data
                modules[subpath]['path'] = subpath
    return modules


def git(args: list, cwd: str) -> str:
    p = subprocess.run(
        ['git'] + args, cwd = cwd, capture_output = True, text = True, check = True,
    )
    return p.stdout.strip()


def fetch_tags(abspath: str):
    shallow = git(['rev-parse', '--is-shallow-repository'], cwd=abspath)
    is_shallow = shallow == 'true'
    args = ['fetch', '--unshallow', '--tags'] if is_shallow else ['fetch', '--tags']
    result = git(args, cwd=abspath)


class SemverUpdates(NamedTuple):
    path: str
    current: Semver | str
    patch: Semver | None
    minor: Semver | None
    major: Semver | None
    pinned: bool


def check_submodule_updates(module: dict, root: str) -> SemverUpdates | None:
    path = module['path']
    abspath = os.path.abspath(os.path.join(root, path))
    if not os.path.isdir(abspath):
        raise Exception(f"Cannot find submodule at path: '{abspath}'")

    fetch_tags(abspath)
    head_versions = parse_tags_to_semver(git(['tag', '--points-at', 'HEAD'], abspath).splitlines())
    all_versions = parse_tags_to_semver(git(['tag', '-l'], abspath).splitlines())
    current = max(head_versions) if head_versions else None
    pinned = (not 'branch' in module)
    patch, minor, major = find_updates(current, all_versions)

    return SemverUpdates(
        path  =  path, current=current,
        patch  =  patch, minor=minor, major = major,
        pinned = pinned,
    )


def print_updates_table(results: list[SemverUpdates]) -> None:
    headers = [field.capitalize() for field in SemverUpdates._fields]
    rows = [
        [r.path,
         r.current.tag if r.current else '-',
         r.patch.tag if r.patch else '-',
         r.minor.tag if r.minor else '-',
         r.major.tag if r.major else '-']
        for r in results
    ]
    widths = [max(len(c) for c in col) for col in zip(headers, *rows)]
    fmt = '  '.join(f'{{:<{w}}}' for w in widths)
    print(fmt.format(*headers))
    for row in rows:
        print(fmt.format(*row))


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Check git submodules for newer semver releases.',
    )
    parser.add_argument('root', nargs='?', default='.', help='repository root (default: cwd)')
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    try:
        git_root = git(['rev-parse', '--show-toplevel'], root)
    except subprocess.CalledProcessError as e:
        print(e.stderr.strip())
        sys.exit(1)

    modules = parse_gitmodules(git_root)
    results = [r for module in modules.values() if (r := check_submodule_updates(module, git_root))]
    print_updates_table(results)


if __name__ == '__main__':
    main()

