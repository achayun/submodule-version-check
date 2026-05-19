import argparse
import configparser
import json
import os
import re
import subprocess
import sys
from typing import NamedTuple, NoReturn

# Regex to break a semver string to a tuple.
# Based on: https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
# Modifications:
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


def check_submodule_clean(path: str, root: str) -> str | None:
    abspath = os.path.abspath(os.path.join(root, path))
    if not os.path.isfile(os.path.join(abspath, '.git')):
        return(f"submodule not initialized")
    if git(['status', '--porcelain', '--untracked-files=no'], cwd=abspath):
        return "working tree has uncommitted changes"
    head = git(['rev-parse', '--short', 'HEAD'], cwd=abspath)
    recorded = git(['rev-parse', '--short', f'HEAD:{path}'], cwd=root)
    if head != recorded:
        return f"HEAD {head} does not match recorded gitlink {recorded}"
    return None


def update_submodule(path: str, root: str, tag: str) -> str:
    abspath = os.path.abspath(os.path.join(root, path))
    git(['checkout', '--recurse-submodules', tag], cwd=abspath)
    git(['add', abspath], cwd=root)
    return git(['rev-parse', '--short', 'HEAD'], cwd=abspath)


class SemverUpdates(NamedTuple):
    path: str
    current: Semver | str
    patch: Semver | None
    minor: Semver | None
    major: Semver | None
    branch: str | None


class UpdateResult(NamedTuple):
    path: str
    from_ver: Semver | None
    from_sha: str | None
    to_ver: Semver | None
    to_sha: str | None
    skip_reason: str | None


def latest_ver(update_policy: str, update: SemverUpdates) -> Semver | None:
    if update_policy == 'patch' and update.patch:
        return update.patch
    elif update_policy == 'minor' and (update.minor or update.patch):
        return max(filter(None, [update.minor, update.patch]))
    elif update_policy == 'major' and (update.major or update.minor or update.patch):
        return max(filter(None, [update.major, update.minor, update.patch]))
    return None


def update_submodules(root: str, updates: list[SemverUpdates], update_policy: str) -> list[UpdateResult]:
      results: list[UpdateResult] = []
      for update in updates:
          abspath = os.path.abspath(os.path.join(root, update.path))
          current_sha = git(['rev-parse', '--short', 'HEAD'], cwd=abspath)
          to_ver, to_sha, skip_reason = None, None, None
          if update.branch:
              skip_reason = f"not pinned, following branch {update.branch}"
          elif module_err := check_submodule_clean(update.path, root):
              skip_reason = f"module state not clean: {module_err}"
          elif to_ver := latest_ver(update_policy, update):
              to_sha = update_submodule(update.path, root, to_ver.tag)
          else:
              skip_reason = "no suitable update found"
          results.append(UpdateResult(update.path, update.current, current_sha, to_ver, to_sha, skip_reason))
      return results


def update_kind(from_ver: Semver, to_ver: Semver) -> str:
    f = next(
        (i for i, (x, y) in enumerate(zip(from_ver, to_ver)) if x != y),
        None,
    )
    return Semver._fields[f]


COMMIT_MSG_FILENAME = 'GUSTAV_COMMIT_MSG'


def write_commit_message(root: str, message: str) -> str:
    path = os.path.join(root, COMMIT_MSG_FILENAME)
    with open(path, 'w') as f:
        f.write(message)
    return path


def print_commit_hint(msg_path: str) -> None:
    print(f"\nCommit message saved to {msg_path}")
    print(f"  Edit:     git commit -F {msg_path} -e")
    print(f"  Commit:   git commit -F {msg_path}")


def format_commit_message(results: list[UpdateResult]) -> str:
    lines = []
    updated = [r for r in results if r.to_ver is not None]
    skipped = [r for r in results if r.to_ver is None]
    if len(updated):
        lines.append(f"\nUpdated {len(updated)} module{'s' if len(updated) > 1 else ''}:")
    for r in updated:
        from_ver = r.from_ver.tag if r.from_ver else '-'
        kind = update_kind(r.from_ver, r.to_ver) if r.from_ver else 'major'
        lines.append(f"\t{r.path}: {kind} update {r.from_sha} ({from_ver}) -> {r.to_sha} ({r.to_ver.tag})")
    if len(skipped):
        lines.append(f"\nSkipped {len(skipped)} module{'s' if len(skipped) > 1 else ''}:")
    for r in skipped:
        lines.append(f"\t{r.path}: {r.skip_reason}")
    return '\n'.join(lines)


def check_submodule_updates(module: dict, root: str) -> SemverUpdates | None:
    path = module['path']
    abspath = os.path.abspath(os.path.join(root, path))
    if not os.path.isfile(os.path.join(abspath, '.git')):
        raise Exception(f"Cannot find submodule at path: '{abspath}'")

    fetch_tags(abspath)
    head_versions = parse_tags_to_semver(git(['tag', '--points-at', 'HEAD'], abspath).splitlines())
    all_versions = parse_tags_to_semver(git(['tag', '-l'], abspath).splitlines())
    current = max(head_versions) if head_versions else None
    branch = module['branch'] if 'branch' in module else None
    patch, minor, major = find_updates(current, all_versions)

    return SemverUpdates(
        path  =  path, current=current,
        patch  =  patch, minor=minor, major = major,
        branch = branch,
    )


def print_updates_table(results: list[SemverUpdates]) -> None:
    headers = [field.capitalize() for field in SemverUpdates._fields]
    rows = [
        [r.path,
         r.current.tag if r.current else '-',
         r.patch.tag if r.patch else '-',
         r.minor.tag if r.minor else '-',
         r.major.tag if r.major else '-',
         r.branch if r.branch else '-',
        ]
        for r in results
    ]
    widths = [max(len(c) for c in col) for col in zip(headers, *rows)]
    fmt = '  '.join(f'{{:<{w}}}' for w in widths)
    print(fmt.format(*headers))
    for row in rows:
        print(fmt.format(*row))


def fatal(msg: str, exit_code: int) -> NoReturn:
    print(msg)
    sys.exit(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Check git submodules for newer semver releases.',
    )
    parser.add_argument('--root', default='.', help='repository root (default: cwd)')
    parser.add_argument('--update', action='store_true', help='Perform updates on suitable submodules')
    parser.add_argument('--update-policy', default='patch', choices=['patch', 'minor', 'major'], help='Update policy (default: patch)')
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    try:
        git_root = git(['rev-parse', '--show-toplevel'], root)
    except subprocess.CalledProcessError as e:
        fatal(f"error: not inside a git repository: {root}", 127)

    modules = parse_gitmodules(git_root)
    if not modules:
        fatal(f"No submodules found in {git_root}", 0)

    results = [check_submodule_updates(m, git_root) for m in modules.values()]
    print_updates_table(results)

    if not args.update:
        return

    results = update_submodules(git_root, results, args.update_policy)
    message = format_commit_message(results)
    print(message)
    if any(r.to_ver for r in results):
        dot_git_dir = git(['rev-parse', '--absolute-git-dir'], cwd=git_root)
        msg_path = write_commit_message(dot_git_dir, message)
        print_commit_hint(msg_path)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()

