import argparse
import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Optional

_REPO_SCRIPTS_FOLDER_NAME = "conversion"


@lru_cache(maxsize=1)
def _get_repo_root() -> Path:
    """
    Return the nearest ancestor of this file that holds a `.git` entry.

    The entry is a directory in a plain clone and a `gitdir:` file in a linked
    worktree or submodule; both count.
    """
    start_path = Path(__file__).resolve()
    for parent in start_path.parents:
        if (parent / ".git").exists():
            return parent
    raise FileNotFoundError(f"Could not find repo root above {start_path}")


def _bootstrap_sys_path(scripts_folder: str = _REPO_SCRIPTS_FOLDER_NAME) -> None:
    """Put the repo root on sys.path once, so `conversion.*` imports resolve."""
    repo_root = _get_repo_root()
    scripts_dir = repo_root / scripts_folder
    if not scripts_dir.is_dir():
        raise FileNotFoundError(str(scripts_dir))
    root = str(repo_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def _get_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse the command line. The target version is given positionally or by flag:

        run.py v3.17.2
        run.py -v v3.17.2            run.py -vv3.17.2
        run.py --version v3.17.2     run.py --version=v3.17.2
        run.py --target-version v3.17.2  (or --target_version)
        run.py -- v3.17.2

    Unknown flags exit with status 2 (argparse usage error).
    """
    parser = argparse.ArgumentParser(
        prog="run.py",
        description=(
            "Copy the fpm production files into "
            "<DEST_ROOT>/FPM_<version with dots as underscores>, e.g. FPM_3_17_2."
        ),
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="target version, e.g. v3.17.2; prompted for when omitted",
    )
    parser.add_argument(
        "-v", "--version", "--target-version", "--target_version",
        dest="version_flag",
        metavar="VERSION",
        help="target version (same as the positional argument)",
    )
    return parser.parse_args(argv)


def _resolve_version(args: argparse.Namespace) -> str:
    """
    Return the target version from the parsed args, else from an input() prompt.

    Exits with status 2 when the positional and flag values disagree, or when the
    prompt is answered with an empty line or hits EOF (closed or non-interactive
    stdin).
    """
    given = {v.strip() for v in (args.version, args.version_flag) if v and v.strip()}
    if len(given) > 1:
        print(f"Conflicting versions given: {sorted(given)}", file=sys.stderr)
        raise SystemExit(2)
    if given:
        return given.pop()
    try:
        answer = input("Please enter the target version (e.g. v3.17.2): ").strip()
    except EOFError:
        answer = ""
    if not answer:
        print("No target version given.", file=sys.stderr)
        raise SystemExit(2)
    return answer


def main(argv: Optional[List[str]] = None) -> int:
    target_version = _resolve_version(_get_args(argv))

    _bootstrap_sys_path()
    from conversion.prod_deploy import load_project, ProdCopier

    cfg, paths = load_project("fpm", target_version)
    print(str(cfg))

    result = ProdCopier(cfg, paths, dry_run=False).run()

    print(f"{len(result.copied)} files copied.")

    if not result.ok:
        for err in result.errors:
            print(f"\tERROR: {err}", file=sys.stderr)
        print("Failed.", file=sys.stderr)
        return 1

    for sk in result.skipped:
        print(f"\tSkipped: {sk}")
    print("Success!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

