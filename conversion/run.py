import argparse
import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Optional

_GIT_FOLDER_CONTENTS = {"config", "HEAD", "index"}
_REPO_SCRIPTS_FOLDER_NAME = "conversion"

def _is_git_folder(folder) -> bool:
    if not folder.exists():
        return False
    content_names = set(f.name for f in folder.iterdir())
    return content_names.issuperset(_GIT_FOLDER_CONTENTS)

def _search_down_for(folder: Path, name_under: str) -> bool:
    return any(f.name == name_under for f in folder.iterdir())

@lru_cache(maxsize=1)
def _get_repo_root() -> Path:
    start_path = Path(__file__) or Path().cwd()

    all_parents = [start_path] + list(start_path.parents) if start_path.is_dir() else list(start_path.parents)
    for parent in all_parents:
        print(f'Parent: {parent.name}')
        if _search_down_for(parent, ".git"):
            git_folder = parent / ".git"
            if _is_git_folder(git_folder):
                return parent

    raise FileNotFoundError(f'Could not find repo path. Last searched: {parent}')

def _bootstrap_sys_path(scripts_folder: str = _REPO_SCRIPTS_FOLDER_NAME):
    import sys
    repo_root = _get_repo_root()
    scripts_folder = repo_root / scripts_folder

    if not scripts_folder.exists():
        raise FileExistsError(str(scripts_folder))
    sys.path.insert(0, str(scripts_folder))
    sys.path.insert(0, str(scripts_folder.parent))



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
        description="Copy the fpm production files into prod_results/FPM_<version>.",
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
    prompt is answered with an empty line.
    """
    given = {v.strip() for v in (args.version, args.version_flag) if v and v.strip()}
    if len(given) > 1:
        print(f"Conflicting versions given: {sorted(given)}", file=sys.stderr)
        raise SystemExit(2)
    if given:
        return given.pop()
    answer = input("Please enter the target version (e.g. v3.17.2): ").strip()
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

    # Preview
    result = ProdCopier(cfg, paths, dry_run=False).run()

    print(f"{len(result.copied)} files copied.")

    if not result.ok:
        for err in result.errors:
            print(f"\tERROR: {err}")
        print("Failed.")
        return 1

    for sk in result.skipped:
        print(f"\tSkipped: {sk}")
    print("Success!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

