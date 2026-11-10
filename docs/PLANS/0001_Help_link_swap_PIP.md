# Plan 0001: Help link swap

> Rendered by `plan.py render` from `0001_Help_link_swap_ActionPlan.json`. Change the JSON through the driver, then render again; edits to this file are overwritten.

**Plan created:** 2026-11-09
**Spec:** `E:/automation/toolboxes/floodplain_development/docs/superpowers/specs/2026-11-09-toolbox-help-links-design.md`
**Branch:** 0003-help-link-swap -> 0002-python-env
**Base commit:** `33fe6c3`
**Frozen:** 2026-11-10 at `932b3ab`
**Execution model:** serial

## Decisions

- **D1** Which file: hrefs fail the production swap? Spec Section 4 errors on any file:///<drive>:/ href left after the swap; Section 1 calls any file: href outside the checkout prefix an error. project_definitions/fpm.env:5 sets a local DEST_ROOT (E:/automation/Production_Convert/prod_results) and no HELP_ROOT, so under the Section 4 wording every run whose archive holds a link swaps to a file:///E:/ href and fails. Chosen: `file-foreign-unc-target` (Chosen, amended: after the swap, every file: href (the scheme matched as (?i)\bfile:/, so prose such as 'Output file: name' never matches) that is not under the target prefix (compared ignoring case) is an error naming the member and the href, UNC and drive hrefs alike, also in an archive where nothing matched the old prefix; and when swap_count > 0 and the target prefix is not UNC (file://server/..., not file:///X:/), the result carries one error per archive naming the target and HELP_ROOT. A local DEST_ROOT without HELP_ROOT therefore fails only an archive that holds a link, and writes nothing.). Rejected: `drive-any` (Section 4 as written: after the swap every file:///<drive>:/ href in a scanned member is an error, the swapped ones included; UNC hrefs outside the prefix pass. A local DEST_ROOT then needs a UNC HELP_ROOT, or run.py exits 1 once the archive holds a link.), `drive-foreign` (Only file:///<drive>:/ hrefs the swap did not write are errors; a local DEST_ROOT without HELP_ROOT gives working local links. UNC hrefs outside the prefix pass.), `file-foreign` (Section 1: every file: href (drive or UNC) the old prefix does not match is an error; hrefs the swap wrote never are, whatever the new prefix.). Developer accepted the recommendation on 2026-11-09. Amendment: the non-UNC target error fires only when swap_count > 0.
- **D2** How does a dry run report what it would swap? Spec Section 4 Hook says the dry run 'reports what it would swap'; CopyResult (conversion/prod_deploy.py:118-127) has only copied, skipped, patched and errors, and _patch_debug_override reports nothing in a dry run (conversion/prod_deploy.py:423-424). Chosen: `patched-dest` (A result that is ok with swap_count > 0 adds the dest archive path to patched: in a real run after the write, in a dry run as the would-be path (copied already lists unwritten dest paths in a dry run, conversion/prod_deploy.py:437-438). Otherwise nothing joins patched.). Rejected: `errors-only` (A dry run reports only failures (missing targets, errors) through errors, like the debug-override patch's dry-run silence.), `new-field` (CopyResult gains link_swaps: Tuple[LinkSwapResult, ...] = () filled in both modes; the default keeps the positional constructions at conversion/prod_deploy.py:318, 323, 349 and tests/test_run_exit_code.py:15, 31, 53 valid.). Developer accepted the recommendation on 2026-11-09.
- **D3** project_definitions/fpm.env is tracked (git ls-files lists it; .gitignore:39 '.env' matches only a file named .env) although its line 2 says 'Do not commit this file'. Spec Section 4 puts an optional HELP_ROOT=//srv/share/fpm_releases in it. What does the plan do with the tracked file? Chosen: `example-line` (TASK-1 adds to the tracked fpm.env one comment line stating the purpose and the commented example '# HELP_ROOT=//server/share/fpm_releases'. Untracking the file stays a developer recommendation, not a plan step.). Rejected: `leave` (No change to fpm.env; HELP_ROOT is set by hand where a deploy needs it.), `set-help-root` (TASK-1 adds a live HELP_ROOT line naming the real UNC share the developer gives.), `untrack` (The developer untracks fpm.env (git rm --cached; ignore project_definitions/*.env); the plan adds a tracked fpm.env.example with HELP_ROOT commented.). Developer accepted the recommendation on 2026-11-09.
- **D4** An absent folder marked required: false crashes the copy: validate_source checks only required folders (conversion/prod_deploy.py:107-110), then _copy_folder walks every folder and _recurse calls iterdir() (conversion/prod_deploy.py:270), which raises FileNotFoundError out of ProdCopier.run, dry run included (probed 2026-11-09). Spec Section 4's tool_metadata entry is required: false. Fix it in this plan? Chosen: `skip-absent` (TASK-2 makes _copy_folder return empty lists for an absent folder with required: false: no error, no traceback, dry run included, with a test. conversion/prod_deploy.py joins TASK-2's files, and TASK-2 depends on TASK-1 since both edit prod_deploy.py.). Rejected: `keep-crash` (No change: tool_metadata exists in the source checkout, and required: false stays as nominal as it already is for reference.). Developer accepted the recommendation on 2026-11-09.

## Values

| Name | Value | Source | Assumes |
|---|---|---|---|
| old link prefix | Path(SOURCE_ROOT).as_uri() + '/' | spec Section 1; Section 4 LinkSwap | - |
| new link prefix | (help_root or dest_root).as_uri() + '/' | spec Section 4 LinkSwap | - |
| release folder name | FPM_<version without leading v, dots as underscores>, e.g. FPM_3_17_2 | conversion/prod_deploy.py:34-35 | - |
| scanned member suffixes | .xml, .rc, .content | spec Section 4 Module | - |
| live archive members | 266 entries: 47 .content, 47 .rc, 47 .xml, 42 .link (relative script paths, no 'file:' text), 34 .py, 3 .png, 46 directory entries; files deflated (8), directories stored (0) | floodplain_mapping.atbx in E:/automation/toolboxes/floodplain_development (branch 0019-html-metadata), read-only zipfile probe 2026-11-09 | - |
| live archive file: hrefs | 1 member: SmoothAndSimplifyPolygons.tool/tool.content.rc, JSON-escaped as <a href=\"file:///E:/automation/toolboxes/floodplain_development/tool_metadata/tool_help/smooth_simplify.html\">; no other member of any type contains 'file:' | floodplain_mapping.atbx in E:/automation/toolboxes/floodplain_development (branch 0019-html-metadata), read-only zipfile probe 2026-11-09 | - |
| live archive byte-order marks | none: every .xml starts '<?x', every .rc and .content starts '{' then a newline | floodplain_mapping.atbx in E:/automation/toolboxes/floodplain_development (branch 0019-html-metadata), read-only zipfile probe 2026-11-09 | - |
| href tail terminators | double quote, single quote, backslash, <, >, &, #, ? and whitespace; Path.as_uri() percent-encodes each of them (probe: 'E:/a b/c&d#e' -> file:///E:/a%20b/c%26d%23e) | spec Section 4 Module; live archive .rc (see the 'live archive file: hrefs' value); probe 2026-11-09 | - |
| UNC link prefix | Path('//srv/share/fpm_releases/FPM_1_0_0').as_uri() == 'file://srv/share/fpm_releases/FPM_1_0_0' (probe 2026-11-09, Windows) | spec Section 1 | - |
| fnmatch scope | 'tool_help/*.html' also matches .html files in any tool_help/ subfolder no deny pattern removes ('*' crosses '/'), and ignores case on Windows ('tool_help/Upper.HTML' shipped in the probe) | conversion/prod_deploy.py:134-137; probe 2026-11-09 | - |
| red interpreter | HARNESS_PY C:/Users/t968rs/miniforge3/envs/arc_3_4_0/python.exe: Python 3.11.10, pydantic 2.4.2, pytest 7.4.3 (the repo .venv is 3.14.3 / 2.14.2 / 9.2.0) | hpy candidate order (HARNESS_PY first); probe 2026-11-09 | - |
| file href scheme | (?i)\bfile:/ followed by the tail characters | D1 as amended by the developer on 2026-11-09 | file-foreign-unc-target |
| UNC target prefix | the target prefix is UNC when it matches (?i)^file://[^/] (file://server/...); file:///X:/ is a drive | D1 as amended by the developer on 2026-11-09 | file-foreign-unc-target |
| non-UNC target error | one error per archive, only when swap_count > 0, naming the target prefix and HELP_ROOT | D1 as amended by the developer on 2026-11-09 | file-foreign-unc-target |
| patched rule | ok and swap_count > 0 -> the dest archive path joins patched (real run after the write, dry run as the would-be path) | D2 | patched-dest |
| fpm.env example | '# HELP_ROOT=//server/share/fpm_releases' after one purpose comment line; parsed as a comment, so no HELP_ROOT key | D3 | example-line |
| absent optional folder | _copy_folder returns ([], [], []) when source_root / name is not a directory | D4 | skip-absent |
| shipped set | frozenset(p.relative_to(dest_root).as_posix() for p in copied), in both modes; the tail of every href under new_prefix, swapped or already present, is URL-decoded and compared with it ignoring case (casefold) | review R7, adopted by the developer on 2026-11-09: a departure from spec Section 4, which checks targets on disk under check_root | - |

## Formats

- **development help href (old prefix + repo path)**: `file:///E:/automation/toolboxes/floodplain_development/tool_metadata/tool_help/smooth_simplify.html`, copied from `project_definitions/fpm.env:4`
- **HELP_ROOT key in <project>.env (KEY=VALUE, quotes stripped)**: `HELP_ROOT=//srv/share/fpm_releases`, copied from `conversion/prod_deploy.py:53`
- **release folder appended to DEST_ROOT and HELP_ROOT**: `FPM_3_17_2`, copied from `conversion/prod_deploy.py:35`

## Sweeps

- **S1** `ProjectPaths\(`: `conversion/prod_deploy.py` (_load_paths builds it by keyword; TASK-1 adds help_root), `docs/PR_REVIEWS/0001_First.json` (review text quoting a test construction; no change), `tests/test_prod_deploy_dirty.py` (positional two-field construction; help_root defaults to None), `tests/test_prod_deploy_tracked.py` (positional two-field constructions; help_root defaults to None)
- **S2** `ProdCopier|load_project`: `conversion/prod_deploy.py` (definitions and docstring usage; TASK-4 hooks run, load_project keeps its signature), `conversion/run.py` (the CLI caller: load_project('fpm', version) then ProdCopier(..., dry_run=False).run(); a swap error fails the run with exit 1; unchanged), `docs/PR_REVIEWS/0001_First.json` (historical review text; no change), `tests/test_prod_deploy_dirty.py` (real ProdCopier runs with top_level_files ['*.md']: no archive, the hook returns before building a LinkSwap), `tests/test_prod_deploy_tracked.py` (real ProdCopier runs with top_level_files ['*.md']: no archive), `tests/test_run_exit_code.py` (monkeypatches load_project and ProdCopier on prod_deploy; the fake never runs the hook; unchanged)
- **S3** `CopyResult`: `conversion/prod_deploy.py` (definition and three positional constructions; unchanged unless D2 is new-field), `docs/PR_REVIEWS/0001_First.json` (historical review text; no change), `tests/test_run_exit_code.py` (positional four-field constructions; valid under every D2 option)
- **S4** `HELP_ROOT|help_root|help_links|LinkSwap|swap_atbx_links`: no hits
- **S5** `SOURCE_ROOT|DEST_ROOT`: `conversion/prod_deploy.py` (the env parser and docstrings; TASK-1 adds HELP_ROOT beside them), `conversion/run.py` (argparse description names <DEST_ROOT>/FPM_<version>; unchanged), `docs/PR_REVIEWS/0001_First.json` (historical review text; no change), `project_definitions/fpm.env` (the tracked producer of SOURCE_ROOT and DEST_ROOT (D3))
- **S6** `\.atbx`: `dev2prod_DEP.py` (deprecated script naming floodplain_mapping.atbx; no ProdCopier use; untouched), `project_definitions/fpm.json` (top_level_files '*.atbx': the archive TASK-4 swaps), `project_definitions/prod_deploy.json` (second definition with '*.atbx'; no prod_deploy.env exists, so load_project('prod_deploy') fails in _load_paths; untouched)
- **S7** `dry_run`: `conversion/prod_deploy.py` (ProdCopier dry-run branches; TASK-4 adds the read-only source scan), `conversion/run.py` (always dry_run=False; unchanged), `docs/PR_REVIEWS/0001_First.json` (historical review text; no change)
- **S8** `tool_help|tool_metadata`: no hits

## Tasks

### TASK-1: ProjectPaths.help_root and optional HELP_ROOT parsing in _load_paths

**Status:** COMPLETE | **Model:** haiku | **Depends on:** none
**Files:** `conversion/project_model.py`, `conversion/prod_deploy.py`, `tests/test_prod_deploy_help_root.py`, `project_definitions/fpm.env`

**Anchors:**
- `conversion/project_model.py:4` holds `from typing import List, Union`
- `conversion/project_model.py:13-16` holds `@dataclass(frozen=True) class ProjectPaths: source_root: Path dest_root: Path`
- `conversion/prod_deploy.py:34-35` holds `def _generate_project_version_folder_name(project_name: str, version_name: str) -> str:`
- `conversion/prod_deploy.py:53` holds `key, _, value = line.partition("=")`
- `conversion/prod_deploy.py:58-62` holds `def _load_paths(env_path: Path, target_version: str) -> ProjectPaths: data = _parse_env(env_path) missing = [k for k in ("SOURCE_ROOT", "DEST_ROOT") if k not in data]`
- `conversion/prod_deploy.py:63-69` holds `return ProjectPaths( source_root=Path(data["SOURCE_ROOT"]), dest_root=Path( data["DEST_ROOT"]) / _generate_project_version_folder_name( env_path.stem, target_version ),`
- `conversion/prod_deploy.py:94-97` holds `paths = _load_paths(base / f"{name}.env", target_version)`
- `conversion/prod_deploy.py:7` holds `<project>.env -- SOURCE_ROOT and DEST_ROOT paths`
- `conversion/run.py:99` holds `cfg, paths = load_project("fpm", target_version)`
- `tests/test_prod_deploy_tracked.py:50` holds `ProdCopier(_config(tracked_only), ProjectPaths(src, dst)).run()`
- `tests/test_prod_deploy_tracked.py:83` holds `result = ProdCopier(_config(), ProjectPaths(src, dst)).run()`
- `tests/test_prod_deploy_dirty.py:52` holds `return ProjectPaths(src, tmp_path / "dst")`
- `project_definitions/fpm.env:1-5` holds `# fbs project paths # Do not commit this file. SOURCE_ROOT=E:/automation/toolboxes/floodplain_development DEST_ROOT=E:/automation/Production_Convert/prod_results`

1. Copy docs/PLANS/0001/tests/tests/test_prod_deploy_help_root.py to tests/test_prod_deploy_help_root.py.
2. conversion/project_model.py: add Optional to the typing import; ProjectPaths gains a third field `help_root: Optional[Path] = None` after dest_root. The default keeps every positional two-field construction valid (tests/test_prod_deploy_tracked.py:50 and :83, tests/test_prod_deploy_dirty.py:52).
3. conversion/prod_deploy.py `_load_paths`: compute the release folder once with `_generate_project_version_folder_name(env_path.stem, target_version)`; dest_root = Path(DEST_ROOT) / folder as today; help_root = Path(HELP_ROOT) / folder when the HELP_ROOT key is present with a non-empty value, else None. An empty value counts as absent: Path('') / folder is a relative path, which as_uri() rejects later. SOURCE_ROOT and DEST_ROOT stay required; HELP_ROOT is never required. _parse_env already strips surrounding quotes.
4. Module docstring line 7: `<project>.env -- SOURCE_ROOT and DEST_ROOT paths; optional HELP_ROOT (replaces DEST_ROOT in help links only)`.
5. project_definitions/fpm.env (D3 = example-line): after the DEST_ROOT line add one comment line stating the purpose, e.g. '# Optional: UNC share the help links point at (FPM_<version> is appended); DEST_ROOT stays the copy target.', then the commented example '# HELP_ROOT=//server/share/fpm_releases'. _parse_env skips comment lines, so the tracked file still defines no HELP_ROOT. The file stays tracked; untracking it is the developer's call.

- [x] Test `tests/test_prod_deploy_help_root.py::test_help_root_gets_the_release_folder` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_root.py::test_help_root_absent_is_none` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_root.py::test_empty_help_root_is_none` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_root.py::test_two_field_construction_keeps_working` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_root.py::test_load_project_reads_help_root` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_root.py::test_fpm_env_shows_help_root_as_a_comment` fails with AssertionError, then passes
- [x] Run `python -m pytest tests/test_prod_deploy_help_root.py tests/test_prod_deploy_tracked.py tests/test_prod_deploy_dirty.py tests/test_run_exit_code.py -q`: every named test passes; no 'failed' or 'error' in the summary line
- [x] Run `python -m ruff check conversion/project_model.py conversion/prod_deploy.py tests/test_prod_deploy_help_root.py`: All checks passed!
- [x] Record it: `plan.py record 0001 TASK-1 --sha <sha>` or `--staged`

**Evidence:** staged tree cbc8ec9: 6 test node(s) passed

**Recorded:** 2026-11-10, staged, tree `cbc8ec9`
- `python -m pytest -q -p no:cacheprovider --tb=auto tests/test_prod_deploy_help_root.py::test_help_root_gets_the_release_folder tests/test_prod_deploy_help_root.py::test_help_root_absent_is_none tests/test_prod_deploy_help_root.py::test_empty_help_root_is_none tests/test_prod_deploy_help_root.py::test_two_field_construction_keeps_working tests/test_prod_deploy_help_root.py::test_load_project_reads_help_root tests/test_prod_deploy_help_root.py::test_fpm_env_shows_help_root_as_a_comment`

### TASK-2: Ship tool_metadata/tool_help pages through fpm.json; skip an absent optional folder

**Status:** COMPLETE | **Model:** haiku | **Depends on:** TASK-1
**Files:** `project_definitions/fpm.json`, `conversion/prod_deploy.py`, `tests/test_fpm_json_help_pages.py`

**Anchors:**
- `project_definitions/fpm.json:9` holds `"top_level_files": ["README.md", "CHANGELOG.md", "LICENSE", "*.atbx"],`
- `project_definitions/fpm.json:18-26` holds `"name": "reference", "required": false, "allowed": [], "denied": ["reference_modules/**", "toolbox_figures/**", "env/**", "db/**", "git_curated/**", "esri_docs/**", "field_maps/gdb_schemas/**", "esriCRS/_runtime_cache.json"] } ]`
- `conversion/prod_deploy.py:134-137` holds `def _matches(name: str, rel_posix: str, pattern: str) -> bool: if "/" in pattern or "**" in pattern: return fnmatch.fnmatch(rel_posix, pattern) return fnmatch.fnmatch(name, pattern)`
- `conversion/prod_deploy.py:146-149` holds `return any( _matches(name, rel_posix, p) for p in local_denied + global_denied )`
- `conversion/prod_deploy.py:152-155` holds `def _is_allowed(name: str, rel_posix: str, allowed: List[str]) -> bool: if not allowed: return True return any(_matches(name, rel_posix, p) for p in allowed)`
- `conversion/prod_deploy.py:270-276` holds `for item in sorted(dir_path.iterdir()): rel_posix = item.relative_to(root).as_posix() if item.is_dir(): if not _is_denied(item.name, rel_posix, local_denied, global_denied): _recurse(`
- `conversion/prod_deploy.py:277-285` holds `elif item.is_file(): if ( not _is_denied(item.name, rel_posix, local_denied, global_denied) and _is_allowed(item.name, rel_posix, allowed) ): if tracked is None or rel_posix in tracked: acc.append(item) else: untracked.append(item)`
- `conversion/prod_deploy.py:107-110` holds `candidate = paths.source_root / spec.name if spec.required and not candidate.is_dir(): errors.append(f"required folder absent: {candidate}")`
- `conversion/prod_deploy.py:367-374` holds `src_root = self._paths.source_root / spec.name files, untracked = _walk_folder( src_root,`
- `conversion/project_model.py:45-47` holds `Patterns without "/" are matched against the filename only. Patterns with "/" or "**" are matched against the full relative posix path.`
- `conversion/project_model.py:29-30` holds `denied: Glob patterns that unconditionally exclude a file or directory, even if it matches allowed. Evaluated before allowed.`

1. Copy docs/PLANS/0001/tests/tests/test_fpm_json_help_pages.py to tests/test_fpm_json_help_pages.py.
2. project_definitions/fpm.json: append to folders, after the reference entry, the spec entry verbatim: { "name": "tool_metadata", "required": false, "allowed": ["tool_help/*.html", "tool_help/img/**"], "denied": ["tool_help/_fragments/**", "tool_help/_template.html"] }.
How the entry matches (a real _walk_folder probe on 2026-11-09 shipped exactly the pages and images): every pattern holds '/', so _matches compares the path relative to tool_metadata/ with fnmatch, whose '*' also crosses '/' and which ignores case on Windows (normcase). _recurse prunes a directory only when a deny pattern matches the directory path itself, so tool_help/_fragments is descended, but each file under it matches tool_help/_fragments/** and is denied before allowed is consulted. tools/, the *.xml, *.md and metadata_coverage.json under tool_metadata/ match no allowed pattern and stay out. The tracked filter (tracked_only, default True) still applies: an untracked page is skipped.
3. D4 = skip-absent: in ProdCopier._copy_folder, return ([], [], []) when the source folder (source_root / spec.name) is not a directory. validate_source has already refused an absent required folder, so only a required: false folder reaches this; it is skipped with no error and no traceback, dry run included. TASK-2 runs after TASK-1 because both edit conversion/prod_deploy.py.

- [x] Test `tests/test_fpm_json_help_pages.py::test_tool_metadata_folder_is_optional` fails with AssertionError, then passes
- [x] Test `tests/test_fpm_json_help_pages.py::test_walk_ships_pages_and_images_only` fails with AssertionError, then passes
- [x] Test `tests/test_fpm_json_help_pages.py::test_run_ships_tracked_pages_only` fails with AssertionError, then passes
- [x] Test `tests/test_fpm_json_help_pages.py::test_absent_optional_folder_is_skipped[real]` fails with AssertionError, then passes
- [x] Test `tests/test_fpm_json_help_pages.py::test_absent_optional_folder_is_skipped[dry]` fails with AssertionError, then passes
- [x] Run `python -m pytest tests/test_fpm_json_help_pages.py tests/test_prod_deploy_tracked.py -q`: every named test passes; no 'failed' or 'error' in the summary line
- [x] Run `python -m ruff check conversion/prod_deploy.py tests/test_fpm_json_help_pages.py`: All checks passed!
- [x] Record it: `plan.py record 0001 TASK-2 --sha <sha>` or `--staged`

**Evidence:** staged tree 78b3a40: 5 test node(s) passed

**Recorded:** 2026-11-10, staged, tree `78b3a40`
- `python -m pytest -q -p no:cacheprovider --tb=auto tests/test_fpm_json_help_pages.py::test_tool_metadata_folder_is_optional tests/test_fpm_json_help_pages.py::test_walk_ships_pages_and_images_only tests/test_fpm_json_help_pages.py::test_run_ships_tracked_pages_only tests/test_fpm_json_help_pages.py::test_absent_optional_folder_is_skipped[real] tests/test_fpm_json_help_pages.py::test_absent_optional_folder_is_skipped[dry]`

### TASK-3: conversion/help_links.py: LinkSwap, LinkSwapResult and swap_atbx_links

**Status:** COMPLETE | **Model:** opus | **Depends on:** TASK-1
**Files:** `conversion/help_links.py`, `tests/test_help_links.py`

**Anchors:**
- `conversion/project_model.py:13-16` holds `@dataclass(frozen=True) class ProjectPaths: source_root: Path dest_root: Path`
- `conversion/prod_deploy.py:18` holds `from __future__ import annotations`
- `pyproject.toml:25` holds `target-version = "py311"`
- `pyproject.toml:34` holds `ignore = ["UP006", "UP007", "UP035", "UP045"]`
- `tests/conftest.py:3-4` holds `pytest's default import mode inserts the repository root`

0. Precondition: execution waits for the spec's 'Gate: links work in Pro' section (its 'Order of work' puts Section 4 after the gate): the developer has confirmed that ArcGIS Pro follows a file: link from a tool's '?' page. If the gate fails, record this item with --blocked naming the gate result; this precondition does not block the freeze.
1. Copy docs/PLANS/0001/tests/tests/test_help_links.py to tests/test_help_links.py.
2. New module conversion/help_links.py: `from __future__ import annotations`, typing-module hints (Optional, Tuple, List, FrozenSet; no X | Y, per pyproject.toml ruff ignores), functions under 50 lines, no first or second person. It imports only the standard library and conversion.project_model.
   - `@dataclass(frozen=True) class LinkSwap: old_prefix: str; new_prefix: str`, with classmethod `for_paths(paths: ProjectPaths) -> LinkSwap`: old_prefix = paths.source_root.as_uri() + '/', new_prefix = (paths.help_root or paths.dest_root).as_uri() + '/'.
   - `@dataclass(frozen=True) class LinkSwapResult: changed_members: Tuple[str, ...]; swap_count: int; missing_targets: Tuple[str, ...]; errors: Tuple[str, ...]`, with property `ok` = no missing targets and no errors.
   - `swap_atbx_links(atbx: Path, swap: LinkSwap, shipped: FrozenSet[str], apply: bool) -> LinkSwapResult`. shipped holds the repo-relative posix paths of the files the release ships; the caller builds it from ProdCopier's copied list. It replaces spec Section 4's check_root (review R7, adopted by the developer): no link target is ever probed on disk.
3. Read: iterate zf.infolist() and read each member with zf.read(info), never zf.read(name), so every entry is read as itself. Scan only members whose name ends .xml, .rc or .content (ignoring case); tool.content is scanned like the others. Directory entries and every other member (png, py, link) are carried as raw bytes and never decoded, even when they hold the prefix text. Decode a scanned member by its byte-order mark: UTF-8 BOM, UTF-16 LE BOM, UTF-16 BE BOM, else plain UTF-8; keep the encoding and the BOM (one BOM, never doubled). A scanned member that does not decode is an error naming the member.
4. Match: the old prefix, escaped, ignoring case, followed by a tail: the longest run of characters other than double quote, single quote, backslash, '<', '>', '&', '#', '?' and whitespace. The .rc closes an href with a JSON-escaped quote (backslash) and the .xml with &quot; (ampersand), so the tail stops there. Replace only the prefix with new_prefix; the tail never changes, and every other byte of the member is kept (the tests compare whole members byte for byte). Count each replacement in swap_count; '#anchor', http(s) and hrefs the prefix does not match are not rewritten.
5. Targets: every file: href under new_prefix, swapped or already present, has its tail (the text after new_prefix) URL-decoded (urllib.parse.unquote) and checked against shipped, compared ignoring case (casefold: the links resolve on case-insensitive Windows shares). Each absent tail joins missing_targets exactly once however often it occurs, as the href writes it.
6. Foreign file: hrefs (D1 = file-foreign-unc-target, amended): after the swap, search every scanned member, also one where nothing matched the old prefix, for (?i)\bfile:/ followed by tail characters. Each href found that does not start with new_prefix (compared ignoring case) is an error naming the member and the href, drive (file:///Z:/...) and UNC (file://other/share/...) alike. Prose such as 'Output file: name' never matches: no slash follows the colon.
7. Non-UNC target (D1 amendment): when swap_count > 0 and new_prefix does not match (?i)^file://[^/] (a UNC prefix is file://server/...; file:///X:/ is a drive), add one error naming new_prefix and saying to set HELP_ROOT to a UNC share. No such error when swap_count is 0.
8. All or nothing: write only when apply is True, swap_count > 0 and missing_targets and errors are empty; otherwise the archive is never opened for writing. The write goes to a temp file created in atbx.parent, member by member in infolist order: a fresh ZipInfo per member copying filename, date_time, compress_type, external_attr, create_system and comment; a changed member re-encoded in its original encoding with its original BOM; every other member with its original bytes. Validate the temp archive with zipfile.ZipFile (it opens, ZipFile.testzip() returns None, each changed member decodes), then os.replace(temp, atbx). Any failure there (validation, or os.replace refused because the archive is read-only) removes the temp file, adds one error, and leaves the original untouched.
9. Return the result with changed_members in archive order.

- [x] Test `tests/test_help_links.py::test_prefixes_without_help_root` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_help_root_replaces_dest_root_in_links` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_swap_count_and_tail_kept` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_prefix_match_ignores_case` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_byte_order_mark_is_kept[utf-16-be]` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_byte_order_mark_is_kept[utf-16-le]` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_byte_order_mark_is_kept[utf-8-sig]` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_unscanned_members_are_byte_identical` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_anchor_and_http_hrefs_are_left_alone` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_prose_file_colon_is_not_a_link` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_url_encoded_tail_is_decoded_for_the_check` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_tail_check_ignores_case` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_member_order_compression_and_timestamps_are_kept` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_missing_target_writes_nothing` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_page_on_disk_but_not_shipped_is_missing` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_each_missing_tail_is_reported_once` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_link_already_at_the_release_prefix_is_checked` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_shipped_link_already_at_the_release_prefix_is_ok` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_leftover_drive_href_is_an_error` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_lone_lowercase_drive_href_is_an_error` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_foreign_unc_href_is_an_error` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_local_target_with_links_is_one_error` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_local_target_without_links_is_ok` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_read_only_archive_leaves_no_temp_file` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_failed_validation_leaves_no_temp_file` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_dry_run_reports_and_writes_nothing` fails with ImportError, then passes
- [x] Test `tests/test_help_links.py::test_archive_without_links_is_not_rewritten` fails with ImportError, then passes
- [x] Run `python -m pytest tests/test_help_links.py -q`: every named test passes; no 'failed' or 'error' in the summary line
- [x] Run `python -m ruff check conversion/help_links.py tests/test_help_links.py`: All checks passed!
- [x] Record it: `plan.py record 0001 TASK-3 --sha <sha>` or `--staged`

**Evidence:** commit 932b3ab: 27 test node(s) passed

**Recorded:** 2026-11-10, commit `932b3ab`, tree `fc32cca`
- `python -m pytest -q -p no:cacheprovider --tb=auto tests/test_help_links.py::test_prefixes_without_help_root tests/test_help_links.py::test_help_root_replaces_dest_root_in_links tests/test_help_links.py::test_swap_count_and_tail_kept tests/test_help_links.py::test_prefix_match_ignores_case tests/test_help_links.py::test_byte_order_mark_is_kept[utf-16-be] tests/test_help_links.py::test_byte_order_mark_is_kept[utf-16-le] tests/test_help_links.py::test_byte_order_mark_is_kept[utf-8-sig] tests/test_help_links.py::test_unscanned_members_are_byte_identical tests/test_help_links.py::test_anchor_and_http_hrefs_are_left_alone tests/test_help_links.py::test_prose_file_colon_is_not_a_link tests/test_help_links.py::test_url_encoded_tail_is_decoded_for_the_check tests/test_help_links.py::test_tail_check_ignores_case tests/test_help_links.py::test_member_order_compression_and_timestamps_are_kept tests/test_help_links.py::test_missing_target_writes_nothing tests/test_help_links.py::test_page_on_disk_but_not_shipped_is_missing tests/test_help_links.py::test_each_missing_tail_is_reported_once tests/test_help_links.py::test_link_already_at_the_release_prefix_is_checked tests/test_help_links.py::test_shipped_link_already_at_the_release_prefix_is_ok tests/test_help_links.py::test_leftover_drive_href_is_an_error tests/test_help_links.py::test_lone_lowercase_drive_href_is_an_error tests/test_help_links.py::test_foreign_unc_href_is_an_error tests/test_help_links.py::test_local_target_with_links_is_one_error tests/test_help_links.py::test_local_target_without_links_is_ok tests/test_help_links.py::test_read_only_archive_leaves_no_temp_file tests/test_help_links.py::test_failed_validation_leaves_no_temp_file tests/test_help_links.py::test_dry_run_reports_and_writes_nothing tests/test_help_links.py::test_archive_without_links_is_not_rewritten`

### TASK-4: Swap help links in ProdCopier.run after the debug-override patch

**Status:** COMPLETE | **Model:** opus | **Depends on:** TASK-1, TASK-2, TASK-3
**Files:** `conversion/prod_deploy.py`, `tests/test_prod_deploy_help_links.py`

**Anchors:**
- `conversion/prod_deploy.py:28` holds `from conversion.project_model import ProjectPaths, ProdConfig, FolderSpec`
- `conversion/prod_deploy.py:9-11` holds `cfg, paths = load_project("fpm", "v3.17.2") result = ProdCopier(cfg, paths, dry_run=True).run()`
- `conversion/prod_deploy.py:118-127` holds `class CopyResult: copied: Tuple[Path, ...] skipped: Tuple[Path, ...] patched: Tuple[Path, ...] errors: Tuple[str, ...]`
- `conversion/prod_deploy.py:296` holds `dry_run: Walk and filter without writing anything.`
- `conversion/prod_deploy.py:315` holds `def run(self) -> CopyResult:`
- `conversion/prod_deploy.py:340-351` holds `c, s, e = self._copy_top_level() copied.extend(c) skipped.extend(s) errors_acc.extend(e) p, e = self._patch_debug_override() patched.extend(p) errors_acc.extend(e) return CopyResult( tuple(copied), tuple(skipped), tuple(patched), tuple(errors_acc) )`
- `conversion/prod_deploy.py:406-411` holds `dst = self._paths.dest_root / item.name ok, err = self._copy_file(item, dst) if err: errors.append(err) elif ok: copied.append(dst)`
- `conversion/prod_deploy.py:416-424` holds `def _patch_debug_override(self) -> Tuple[List[Path], List[str]]:`
- `conversion/prod_deploy.py:423-424` holds `elif self._dry_run: return patched, errors`
- `conversion/prod_deploy.py:432-433` holds `except Exception as exc: errors.append(f"patch failed {target}: {exc}")`
- `conversion/prod_deploy.py:436-438` holds `def _copy_file(self, src: Path, dst: Path) -> Tuple[bool, Optional[str]]: if self._dry_run: return True, None`
- `conversion/run.py:97-102` holds `from conversion.prod_deploy import load_project, ProdCopier cfg, paths = load_project("fpm", target_version) print(str(cfg)) result = ProdCopier(cfg, paths, dry_run=False).run()`
- `conversion/run.py:106-110` holds `print("Failed.", file=sys.stderr) return 1`
- `tests/test_run_exit_code.py:15` holds `result = CopyResult((), (), (), ())`
- `tests/test_run_exit_code.py:41-42` holds `monkeypatch.setattr(prod_deploy, "load_project", _fake_load_project) monkeypatch.setattr(prod_deploy, "ProdCopier", copier)`
- `tests/test_prod_deploy_tracked.py:37-43` holds `top_level_files=["*.md"],`
- `tests/test_prod_deploy_dirty.py:40-45` holds `top_level_files=["*.md"],`
- `tests/test_prod_deploy_dirty.py:58` holds `result = ProdCopier(_config(), paths).run()`
- `project_definitions/fpm.json:9` holds `"top_level_files": ["README.md", "CHANGELOG.md", "LICENSE", "*.atbx"],`

0. Precondition: execution waits for the spec's 'Gate: links work in Pro' section (its 'Order of work' puts Section 4 after the gate): the developer has confirmed that ArcGIS Pro follows a file: link from a tool's '?' page. If the gate fails, record this item with --blocked naming the gate result; this precondition does not block the freeze.
1. Copy docs/PLANS/0001/tests/tests/test_prod_deploy_help_links.py to tests/test_prod_deploy_help_links.py.
2. conversion/prod_deploy.py: add the module-level import `from conversion.help_links import LinkSwap, swap_atbx_links` beside the project_model import (help_links imports only project_model, so no cycle). The hook calls the module-level name swap_atbx_links, never a function-local import, so monkeypatch.setattr(conversion.prod_deploy, 'swap_atbx_links', ...) replaces it, as test_swap_failure_is_one_error_and_keeps_debug_patch does.
3. ProdCopier.run: after `p, e = self._patch_debug_override()` and its two extends, add `p, e = self._swap_help_links(copied)` and extend patched and errors_acc the same way.
4. New method `_swap_help_links(self, copied: List[Path]) -> Tuple[List[Path], List[str]]`: the archives are the paths in copied whose suffix is .atbx (ignoring case) and whose parent is dest_root (top-level copies land at dest_root / name; in a dry run copied lists those dest paths unwritten). With none, return ([], []) before building a LinkSwap, so runs without an archive (every existing ProdCopier test) never compute a URI. Build LinkSwap.for_paths(self._paths) once; a ValueError there (a relative SOURCE_ROOT or HELP_ROOT) is one error. Build shipped = frozenset(p.relative_to(dest_root).as_posix() for p in copied): copied holds dest paths in both modes, so the set is exactly what this release ships, and a link to an untracked page, a denied path (tool_help/_fragments/, _template.html, tools/*.xml) or a stale file left in dest_root by an earlier run is a missing target (review R7). Real run: swap_atbx_links(dest archive, swap, shipped, apply=True); the source archive is never opened. Dry run: swap_atbx_links(source_root / name, swap, shipped, apply=False): nothing was copied, so the source archive is scanned read-only. Wrap each archive's call in `except Exception as exc`, as _patch_debug_override does (conversion/prod_deploy.py:432-433): an exception is exactly one error string naming the archive and the exception, and the debug-override result already in patched stays. Each missing target becomes one error string naming the archive and the tail (e.g. f"help link target missing in {name}: {tail}"), and each result error one string naming the archive; the D1 non-UNC error therefore reaches CopyResult.errors once per archive. D2 = patched-dest: a result that is ok with swap_count > 0 adds the dest archive path to patched, in a real run after the write and in a dry run as the would-be path; otherwise nothing joins patched.
5. Docstrings: the module docstring and the ProdCopier docstring name the help-link swap of the top-level .atbx copies, after the debug-override patch.

- [x] Test `tests/test_prod_deploy_help_links.py::test_run_swaps_links_in_the_copied_archive` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_run_reports_a_missing_target_and_keeps_the_copy` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_local_dest_without_help_root_is_one_error` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_stale_dest_file_does_not_satisfy_a_link` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_link_to_a_denied_source_file_fails[real]` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_link_to_a_denied_source_file_fails[dry]` fails with AssertionError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_swap_failure_is_one_error_and_keeps_debug_patch` fails with AttributeError, then passes
- [x] Test `tests/test_prod_deploy_help_links.py::test_dry_run_checks_the_source_and_writes_nothing` fails with AssertionError, then passes
- [x] Run `python -m pytest tests/test_prod_deploy_help_links.py tests/test_help_links.py tests/test_fpm_json_help_pages.py tests/test_prod_deploy_help_root.py tests/test_prod_deploy_tracked.py tests/test_prod_deploy_dirty.py tests/test_run_exit_code.py tests/test_run_args.py -q`: every named test passes; no 'failed' or 'error' in the summary line
- [x] Run `python -m ruff check conversion/prod_deploy.py tests/test_prod_deploy_help_links.py`: All checks passed!
- [x] Record it: `plan.py record 0001 TASK-4 --sha <sha>` or `--staged`

**Evidence:** staged tree cdfff33: 8 test node(s) passed

**Recorded:** 2026-11-10, staged, tree `cdfff33`
- `python -m pytest -q -p no:cacheprovider --tb=auto tests/test_prod_deploy_help_links.py::test_run_swaps_links_in_the_copied_archive tests/test_prod_deploy_help_links.py::test_run_reports_a_missing_target_and_keeps_the_copy tests/test_prod_deploy_help_links.py::test_local_dest_without_help_root_is_one_error tests/test_prod_deploy_help_links.py::test_stale_dest_file_does_not_satisfy_a_link tests/test_prod_deploy_help_links.py::test_link_to_a_denied_source_file_fails[real] tests/test_prod_deploy_help_links.py::test_link_to_a_denied_source_file_fails[dry] tests/test_prod_deploy_help_links.py::test_swap_failure_is_one_error_and_keeps_debug_patch tests/test_prod_deploy_help_links.py::test_dry_run_checks_the_source_and_writes_nothing`
