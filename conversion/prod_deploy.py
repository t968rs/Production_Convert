"""
prod_deploy.py - Production deployment config and file copier for fpm projects.

Project definition layout:
    project_definitions/ (sibling of conversion/)
        <project>.json   -- folder specs and file filter patterns
        <project>.env    -- SOURCE_ROOT and DEST_ROOT paths; optional HELP_ROOT (replaces DEST_ROOT in help links only)

Usage:
    cfg, paths = load_project("fpm", "v3.17.2")
    result = ProdCopier(cfg, paths, dry_run=True).run()

tracked_only (default True) requires git on PATH and a repository SOURCE_ROOT.
Tracked files with uncommitted changes are listed in a stderr warning and
copied anyway (working-tree contents, not the committed release).

After the debug-override patch, each top-level .atbx copy has its development
help links (SOURCE_ROOT) swapped to HELP_ROOT, else DEST_ROOT; a link whose
target the release does not ship is an error. A dry run scans the source
archive read-only.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, List, Optional, Tuple
from conversion.help_links import LinkSwap, swap_atbx_links
from conversion.project_model import ProjectPaths, ProdConfig, FolderSpec


_HERE_DIR = Path(__file__).parent.resolve()
_PROJECT_DEF_DIR = _HERE_DIR.parent / "project_definitions"

def _generate_project_version_folder_name(project_name: str, version_name: str) -> str:
    return f"{project_name.upper()}_{version_name.strip('v').strip().replace('.', '_')}"


# ------ Loading Helpers ---------------------------------------------------

def _parse_env(env_path: Path) -> dict:
    """
    Parse a simple KEY=VALUE env file.
    Ignores blank lines and lines starting with #.
    Strips surrounding quotes from values.
    """
    result: dict = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _load_paths(env_path: Path, target_version: str) -> ProjectPaths:
    data = _parse_env(env_path)
    missing = [k for k in ("SOURCE_ROOT", "DEST_ROOT") if k not in data]
    if missing:
        raise KeyError(f"missing keys in {env_path}: {missing}")
    folder = _generate_project_version_folder_name(env_path.stem, target_version)
    help_value = data.get("HELP_ROOT", "")
    return ProjectPaths(
        source_root=Path(data["SOURCE_ROOT"]),
        dest_root=Path(data["DEST_ROOT"]) / folder,
        help_root=Path(help_value) / folder if help_value else None,
    )



# ---------------------------------------------------------------------------
# Project loader
# ---------------------------------------------------------------------------

def load_project(
    name: str,
    target_version: str,
    project_def_dir: Optional[Path] = None,
) -> Tuple[ProdConfig, ProjectPaths]:
    """
    Load config and paths for a named project.

    Resolves both files from project_def_dir (default: project_definitions/,
    sibling of conversion/):
        <name>.json
        <name>.env

    With tracked_only (default True), the copy requires git on PATH and a
    repository SOURCE_ROOT.
    """
    base = project_def_dir or _PROJECT_DEF_DIR
    cfg = ProdConfig.from_json(base / f"{name}.json")
    paths = _load_paths(base / f"{name}.env", target_version)
    return cfg, paths


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_source(config: ProdConfig, paths: ProjectPaths) -> List[str]:
    """Returns one error string per missing required folder."""
    errors: List[str] = []
    for spec in config.folders:
        candidate = paths.source_root / spec.name
        if spec.required and not candidate.is_dir():
            errors.append(f"required folder absent: {candidate}")
    return errors


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CopyResult:
    copied: Tuple[Path, ...]
    skipped: Tuple[Path, ...]
    patched: Tuple[Path, ...]
    errors: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------

def _matches(name: str, rel_posix: str, pattern: str) -> bool:
    if "/" in pattern or "**" in pattern:
        return fnmatch.fnmatch(rel_posix, pattern)
    return fnmatch.fnmatch(name, pattern)


def _is_denied(
    name: str,
    rel_posix: str,
    local_denied: List[str],
    global_denied: List[str],
) -> bool:
    return any(
        _matches(name, rel_posix, p)
        for p in local_denied + global_denied
    )


def _is_allowed(name: str, rel_posix: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    return any(_matches(name, rel_posix, p) for p in allowed)


# ---------------------------------------------------------------------------
# Git tracking
# ---------------------------------------------------------------------------

def _tracked_paths(source_root: Path) -> FrozenSet[str]:
    """
    Return the posix paths, relative to source_root, that git tracks there.

    Reads the index (``git ls-files``), so a staged file counts as tracked.
    Raises RuntimeError when git fails, e.g. source_root is not a repository.
    """
    proc = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z"],
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git ls-files failed in {source_root}: {detail}")
    return frozenset(p for p in proc.stdout.decode("utf-8").split("\0") if p)


def _dirty_tracked_paths(source_root: Path) -> List[str]:
    """
    Return tracked paths under source_root with staged or unstaged changes.

    Paths are relative to the repository root, as ``git status --porcelain``
    reports them. Raises RuntimeError when git fails.
    """
    proc = subprocess.run(
        [
            "git", "-C", str(source_root), "status",
            "--porcelain", "-z", "--untracked-files=no", "--", ".",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git status failed in {source_root}: {detail}")
    return _parse_porcelain_z(proc.stdout.decode("utf-8"))


def _parse_porcelain_z(output: str) -> List[str]:
    """Extract paths from ``status --porcelain -z`` output, dropping rename sources."""
    fields = output.split("\0")
    paths: List[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1  # the next field is the rename or copy source path
    return paths


def _warn_dirty(source_root: Path, dirty: List[str]) -> None:
    """Print the tracked files whose working-tree contents differ from HEAD."""
    print(
        f"WARNING: {len(dirty)} tracked file(s) in {source_root} have "
        "uncommitted changes; copying working-tree contents:",
        file=sys.stderr,
    )
    for rel in dirty:
        print(f"\t{rel}", file=sys.stderr)


def _scope_tracked(
    tracked: Optional[FrozenSet[str]], folder_name: str
) -> Optional[FrozenSet[str]]:
    """Re-root tracked paths at one folder; None (no filtering) passes through."""
    if tracked is None:
        return None
    prefix = folder_name.strip("/") + "/"
    return frozenset(p[len(prefix):] for p in tracked if p.startswith(prefix))


# ---------------------------------------------------------------------------
# Recursive walk (prunes denied directories before descending)
# ---------------------------------------------------------------------------

def _walk_folder(
    folder_root: Path,
    local_denied: List[str],
    global_denied: List[str],
    allowed: List[str],
    tracked: Optional[FrozenSet[str]] = None,
) -> Tuple[List[Path], List[Path]]:
    """
    Return (files to copy, untracked files left out).

    tracked holds paths relative to folder_root; None disables the git filter.
    """
    acc: List[Path] = []
    untracked: List[Path] = []
    _recurse(
        folder_root, folder_root, local_denied, global_denied, allowed, tracked, acc, untracked
    )
    return acc, untracked


def _recurse(
    dir_path: Path,
    root: Path,
    local_denied: List[str],
    global_denied: List[str],
    allowed: List[str],
    tracked: Optional[FrozenSet[str]],
    acc: List[Path],
    untracked: List[Path],
) -> None:
    for item in sorted(dir_path.iterdir()):
        rel_posix = item.relative_to(root).as_posix()
        if item.is_dir():
            if not _is_denied(item.name, rel_posix, local_denied, global_denied):
                _recurse(
                    item, root, local_denied, global_denied, allowed, tracked, acc, untracked
                )
        elif item.is_file():
            if (
                not _is_denied(item.name, rel_posix, local_denied, global_denied)
                and _is_allowed(item.name, rel_posix, allowed)
            ):
                if tracked is None or rel_posix in tracked:
                    acc.append(item)
                else:
                    untracked.append(item)


# ---------------------------------------------------------------------------
# Copier
# ---------------------------------------------------------------------------

class ProdCopier:
    """
    Copies production files from source to dest per a ProdConfig + ProjectPaths.

    dry_run:    Walk and filter without writing anything.
    clean_dest: Delete dest_root before copying (ensures no stale files).

    After the debug-override patch, run swaps the help links of the top-level
    .atbx copies; an archive swapped without error joins patched.
    """

    _DEBUG_PATTERN = re.compile(r"(_debug_override\s*=\s*)True")

    def __init__(
        self,
        config: ProdConfig,
        paths: ProjectPaths,
        dry_run: bool = False,
        clean_dest: bool = False,
    ) -> None:
        self._cfg = config
        self._paths = paths
        self._dry_run = dry_run
        self._clean_dest = clean_dest
        self._tracked: Optional[FrozenSet[str]] = None

    def run(self) -> CopyResult:
        errors = validate_source(self._cfg, self._paths)
        if errors:
            return CopyResult((), (), (), tuple(errors))

        if self._cfg.tracked_only:
            git_error = self._load_tracked()
            if git_error:
                return CopyResult((), (), (), (git_error,))

        if self._clean_dest and not self._dry_run:
            if self._paths.dest_root.exists():
                shutil.rmtree(self._paths.dest_root)

        copied: List[Path] = []
        skipped: List[Path] = []
        patched: List[Path] = []
        errors_acc: List[str] = []

        for spec in self._cfg.folders:
            c, s, e = self._copy_folder(spec)
            copied.extend(c)
            skipped.extend(s)
            errors_acc.extend(e)

        c, s, e = self._copy_top_level()
        copied.extend(c)
        skipped.extend(s)
        errors_acc.extend(e)

        p, e = self._patch_debug_override()
        patched.extend(p)
        errors_acc.extend(e)

        p, e = self._swap_help_links(copied)
        patched.extend(p)
        errors_acc.extend(e)

        return CopyResult(
            tuple(copied), tuple(skipped), tuple(patched), tuple(errors_acc)
        )

    def _load_tracked(self) -> Optional[str]:
        """Load the tracked set and warn on uncommitted edits; return a git error, if any."""
        try:
            self._tracked = _tracked_paths(self._paths.source_root)
            dirty = _dirty_tracked_paths(self._paths.source_root)
        except (OSError, RuntimeError) as exc:
            return str(exc)
        if dirty:
            _warn_dirty(self._paths.source_root, dirty)
        return None

    def _copy_folder(
        self, spec: FolderSpec
    ) -> Tuple[List[Path], List[Path], List[str]]:
        src_root = self._paths.source_root / spec.name
        if not src_root.is_dir():
            return [], [], []
        files, untracked = _walk_folder(
            src_root,
            list(spec.denied),
            list(self._cfg.global_denied),
            list(spec.allowed),
            _scope_tracked(self._tracked, spec.name),
        )
        copied: List[Path] = []
        skipped: List[Path] = list(untracked)
        errors: List[str] = []
        for src_file in files:
            rel = src_file.relative_to(self._paths.source_root)
            dst = self._paths.dest_root / rel
            ok, err = self._copy_file(src_file, dst)
            if err:
                errors.append(err)
            elif ok:
                copied.append(dst)
            else:
                skipped.append(src_file)
        return copied, skipped, errors

    def _copy_top_level(self) -> Tuple[List[Path], List[Path], List[str]]:
        copied: List[Path] = []
        skipped: List[Path] = []
        errors: List[str] = []
        for item in sorted(self._paths.source_root.iterdir()):
            if not item.is_file():
                continue
            if not any(fnmatch.fnmatch(item.name, p) for p in self._cfg.top_level_files):
                skipped.append(item)
                continue
            if _is_denied(item.name, item.name, [], list(self._cfg.global_denied)):
                skipped.append(item)
                continue
            if self._tracked is not None and item.name not in self._tracked:
                skipped.append(item)
                continue
            dst = self._paths.dest_root / item.name
            ok, err = self._copy_file(item, dst)
            if err:
                errors.append(err)
            elif ok:
                copied.append(dst)
            else:
                skipped.append(item)
        return copied, skipped, errors

    def _patch_debug_override(self) -> Tuple[List[Path], List[str]]:
        patched: List[Path] = []
        errors: List[str] = []
        target = self._paths.dest_root / self._cfg.debug_override_rel
        if not target.is_file() and not self._dry_run:
            errors.append(f"debug_override_rel not found in dest: {target}")
            return patched, errors
        elif self._dry_run:
            return patched, errors
        try:
            content = target.read_text(encoding="utf-8")
            new_content, count = self._DEBUG_PATTERN.subn(r"\g<1>False", content)
            if count:
                if not self._dry_run:
                    target.write_text(new_content, encoding="utf-8")
                patched.append(target)
        except Exception as exc:
            errors.append(f"patch failed {target}: {exc}")
        return patched, errors

    def _swap_help_links(self, copied: List[Path]) -> Tuple[List[Path], List[str]]:
        """
        Swap help links in the top-level .atbx copies; return (patched, errors).

        shipped is every copied path relative to dest_root, so a link to a file
        the release does not ship is a missing target. An archive joins patched
        only when its swap is ok and changed at least one link (D2).
        """
        dest_root = self._paths.dest_root
        archives = [
            p for p in copied if p.suffix.lower() == ".atbx" and p.parent == dest_root
        ]
        if not archives:
            return [], []
        try:
            swap = LinkSwap.for_paths(self._paths)
        except ValueError as exc:
            return [], [f"help link swap failed: {exc}"]
        shipped = frozenset(p.relative_to(dest_root).as_posix() for p in copied)
        patched: List[Path] = []
        errors: List[str] = []
        for dest_atbx in archives:
            swapped, errs = self._swap_archive(dest_atbx, swap, shipped)
            errors.extend(errs)
            if swapped:
                patched.append(dest_atbx)
        return patched, errors

    def _swap_archive(
        self, dest_atbx: Path, swap: LinkSwap, shipped: FrozenSet[str]
    ) -> Tuple[bool, List[str]]:
        """
        Swap one archive: the dest copy in a real run, the source read-only in a dry run.

        Returns (swapped, errors); swapped is True when the result is ok with links swapped.
        """
        name = dest_atbx.name
        target = self._paths.source_root / name if self._dry_run else dest_atbx
        try:
            result = swap_atbx_links(target, swap, shipped, apply=not self._dry_run)
        except Exception as exc:
            return False, [f"help link swap failed {target}: {exc}"]
        errors = [f"help link target missing in {name}: {tail}" for tail in result.missing_targets]
        errors.extend(f"help link error in {name}: {err}" for err in result.errors)
        return result.ok and result.swap_count > 0, errors

    def _copy_file(self, src: Path, dst: Path) -> Tuple[bool, Optional[str]]:
        if self._dry_run:
            return True, None
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True, None
        except Exception as exc:
            return False, f"copy failed {src} -> {dst}: {exc}"
