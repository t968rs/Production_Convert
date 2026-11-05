from pathlib import Path
from functools import lru_cache

TARGET_VERSION = "v3.17.1-beta"
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



def main():
    target_version = input("Please enter the target version (e.g. v3.17.1-beta): ") or TARGET_VERSION

    _bootstrap_sys_path()
    from conversion.prod_deploy import load_project, ProdCopier

    cfg, paths = load_project("fpm", target_version)
    print(str(cfg))

    # Preview
    result = ProdCopier(cfg, paths, dry_run=False).run()

    print(f"{len(result.copied)} files copied.")
    assert result.ok, result.errors

    if result.ok:
        for sk in result.skipped:
            print(f"\tSkipped: {sk}")
        print("Success!")

if __name__ == "__main__":
    SystemExit(main())

