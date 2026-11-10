# Production_Convert

Builds a production release folder from a development checkout of an ArcGIS Pro toolbox project, and
converts the project's `CHANGELOG.md` into a styled Word document for toolbox users.

A release run:

1. copies the git-tracked files a project definition allows into `<DEST_ROOT>/FPM_<version>`;
2. sets `_debug_override = True` to `False` in the copied package when present;
3. rewrites the help links inside each copied `.atbx` from the development checkout to the release folder,
   and checks that every linked help page ships with the release.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and git on `PATH`. Python is pinned to 3.14 by `.python-version`;
uv installs it when missing.

```powershell
cd E:\automation\Production_Convert
uv sync
```

`uv sync` creates `.venv` with the runtime dependencies and the dev group (pytest, ruff). Prefix every
command below with `uv run` so it runs in that environment.

## Release a version

1. Commit or stash work in the source checkout. Only tracked files are copied, and tracked files with
   uncommitted changes are copied as they are on disk (the run lists them in a warning).
2. Check `project_definitions/fpm.env` (see [Configure paths](#configure-paths)). Set `HELP_ROOT` when
   the toolbox archive holds help links.
3. Run the copy:

   ```powershell
   uv run python conversion/run.py v3.17.2
   ```

   With `DEST_ROOT=E:/automation/Production_Convert/prod_results`, this writes
   `E:\automation\Production_Convert\prod_results\FPM_3_17_2`.

4. Read the last line. `Success!` (exit code 0) means the folder can ship. `Failed.` (exit code 1) is
   preceded by one `ERROR:` line per problem and a `NOT SHIPPABLE:` line; do not copy that folder to the
   release share.

The version can be given in any of these forms; with none, the script prompts for it:

```powershell
uv run python conversion/run.py v3.17.2
uv run python conversion/run.py -v v3.17.2
uv run python conversion/run.py --version v3.17.2
uv run python conversion/run.py --target-version v3.17.2
```

The folder name drops a leading `v` and replaces dots with underscores: `v3.17.2` becomes `FPM_3_17_2`.
Conflicting versions (a positional value and a different flag value), an empty prompt answer and
unknown flags exit with code 2.

The run writes over files already in the release folder but never deletes any. To rebuild a version
from scratch, delete its `FPM_<version>` folder first.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Every file copied, debug switch patched when present, and every help link in a copied archive swapped and shipped. |
| 1 | At least one error; the release folder, if written, is not shippable. |
| 2 | Usage error: no version, conflicting versions or an unknown flag. |

### Common errors

| Message | Cause | Fix |
|---|---|---|
| `required folder absent: ...` | A folder marked `"required": true` in `fpm.json` is missing from `SOURCE_ROOT`. | Point `SOURCE_ROOT` at the right checkout, or mark the folder optional. |
| `git ls-files failed in ...` | `SOURCE_ROOT` is not a git repository. | Point `SOURCE_ROOT` at the git checkout. |
| `git not found on PATH: ...` | git is not installed or not on `PATH`. | Install git or add it to `PATH`. |
| `debug_override_rel not found in dest: ...` | The file named by `debug_override_rel` was not copied. | Check that the path is right and that the file is tracked and allowed. |
| `help link target missing in <archive>: <path>` | A tool's help page links a file the release does not ship. | Track and allow the file (for example under `tool_metadata/tool_help/`), or fix the link in the toolbox. |
| `help link error in <archive>: ...` | A link points outside the development checkout, or the new prefix is not a UNC path. | Set `HELP_ROOT` to the UNC release share. |

## Configure paths

`project_definitions/fpm.env` holds the machine paths, one `KEY=VALUE` per line. A line starting with `#` is a
comment; trailing comments after a value are not supported:

```ini
SOURCE_ROOT=E:/automation/toolboxes/floodplain_development
DEST_ROOT=E:/automation/Production_Convert/prod_results
# HELP_ROOT=//server/share/fpm_releases
```

| Key | Required | Meaning |
|---|---|---|
| `SOURCE_ROOT` | yes | The development checkout to copy from; must be a git repository. |
| `DEST_ROOT` | yes | Where the `FPM_<version>` folder is written. |
| `HELP_ROOT` | once the archive holds help links | The UNC share the release is served from. Help links point at `HELP_ROOT/FPM_<version>`; files are still written under `DEST_ROOT`. |

`fpm.env` is tracked with these defaults. `project_definitions/fpm.env.example` documents the
`HELP_ROOT` line and is never loaded; the run reads `fpm.env` only.

### Help links

Each tool's help page is linked from the toolbox archive with a `file:` URL under `SOURCE_ROOT`. After
copying, the run rewrites that prefix in the `.xml`, `.rc` and `.content` members of every top-level
`.atbx` in the release folder:

```
file:///E:/automation/toolboxes/floodplain_development/tool_metadata/tool_help/clip.html
    -> file://server/share/fpm_releases/FPM_3_17_2/tool_metadata/tool_help/clip.html
```

Without `HELP_ROOT`, the prefix becomes the local `DEST_ROOT` folder, which users cannot reach. The run
treats that as an error once a link is swapped, so a local `DEST_ROOT` needs a `HELP_ROOT`.

An archive is rewritten all or nothing: one missing target or bad link leaves it untouched, still
pointing at the development checkout. The source archive is never modified.

## Choose what ships

`project_definitions/fpm.json` decides which files are copied. An excerpt of `fpm.json` (the tracked
file denies more globs and lists more folders):

```json
{
  "debug_override_rel": "scripts/fpm/__init__.py",
  "global_denied": ["__pycache__", "*.pyc", ".git", "*.db"],
  "top_level_files": ["README.md", "CHANGELOG.md", "LICENSE", "*.atbx"],
  "folders": [
    { "name": "scripts", "required": true, "allowed": ["fpm/**"], "denied": ["fpm/_tbx_staging/**"] },
    { "name": "calcs", "required": true, "allowed": [], "denied": ["working/**"] }
  ]
}
```

| Field | Meaning |
|---|---|
| `folders[].name` | A folder directly under `SOURCE_ROOT`, copied to the same place in the release. |
| `folders[].required` | `true`: the run fails when the folder is missing. `false`: a missing folder is skipped. |
| `folders[].allowed` | Globs of files to copy, relative to the folder. Empty copies everything not denied. |
| `folders[].denied` | Globs that exclude a file or a whole directory, even when `allowed` matches. |
| `global_denied` | Globs denied in every folder and among the top-level files. |
| `top_level_files` | Globs of files directly under `SOURCE_ROOT` to copy. |
| `debug_override_rel` | Path, relative to the release folder, of the file whose `_debug_override = True` is set to `False`. |
| `tracked_only` | Default `true`: only files git tracks are copied; untracked and ignored files are listed as skipped. |

A glob without `/` matches the file or directory name anywhere (`*.pyc`); a glob with `/` or `**`
matches the path relative to the folder (`fpm/**`).

## Preview a release

The command line always writes. To list what a release would contain without writing anything, call the
copier with `dry_run=True`:

```powershell
uv run python -c "from conversion.prod_deploy import load_project, ProdCopier; cfg, paths = load_project('fpm', 'v3.17.2'); r = ProdCopier(cfg, paths, dry_run=True).run(); print(*r.copied, sep='\n'); print(len(r.copied), 'files'); print(*r.errors, sep='\n')"
```

A dry run checks the help links of the source archive read-only and reports the same link errors a
real run would. With the tracked `fpm.env` (no `HELP_ROOT`) it ends with:

```
help link error in floodplain_mapping.atbx: help links would point at file:///E:/automation/Production_Convert/prod_results/FPM_3_17_2/, which is not a UNC share; set HELP_ROOT to a UNC share (//server/share/...) in the project .env
```

## Convert the changelog to Word

```powershell
uv run python -m conversion.changelog_docx E:\automation\toolboxes\floodplain_development\CHANGELOG.md E:\automation\Production_Convert\prod_results\CHANGELOG.docx --title "Changelog - FPM"
```

| Argument | Meaning |
|---|---|
| `source` | The Markdown changelog to read. |
| `output` | The `.docx` to write; missing parent folders are created. |
| `--title` | Optional replacement for the first `#` heading. |

The document uses Word's built-in heading styles, so the navigation pane lists every release, tool and
change type. Code terms (anything in backticks, plus identifiers found in plain text: snake_case,
camelCase, PascalCase and dotted names, file names and paths) render in a dark red monospace font
inside visible backticks. Any release section with no content (for example an empty `Unreleased`) is
left out with its subheadings, as is the Keep a Changelog boilerplate line.

## Add another project

`run.py` builds the `fpm` project. A project named `<name>` is defined by two files in
`project_definitions/`, `<name>.json` and `<name>.env`, and its release folder is
`<NAME>_<version>`. Load it from Python the same way `run.py` does:

```python
from conversion.prod_deploy import load_project, ProdCopier

cfg, paths = load_project("<name>", "v1.0.0")
result = ProdCopier(cfg, paths).run()
```

## Development

Run the full test suite and lint (`pyproject.toml` limits collection to `tests/`):

```powershell
uv run pytest
uv run ruff check conversion tests
```

To run a single file, name it, for example `uv run pytest tests/test_help_links.py`.

| Path | Role |
|---|---|
| `conversion/run.py` | Command-line entry point for an `fpm` release. |
| `conversion/prod_deploy.py` | Project loading, file selection, copy, debug patch and help-link step. |
| `conversion/help_links.py` | Help-link rewrite inside one `.atbx` archive. |
| `conversion/project_model.py` | `ProjectPaths` and the `fpm.json` models. |
| `conversion/changelog_docx.py` | Markdown changelog to `.docx`. |
| `project_definitions/` | Per-project copy rules (`.json`) and paths (`.env`). |
| `project_definitions/prod_deploy.json` | Earlier project definition; has no `prod_deploy.env`, so it cannot be loaded. Not used by `run.py`. |
