"""Help-link swap inside a copied ArcGIS Pro toolbox archive (.atbx).

A tool's help text in the archive links its help page with a file: href under the development
checkout (SOURCE_ROOT). The production copy rewrites that prefix to the release folder (HELP_ROOT
when set, else DEST_ROOT) and checks every link under that release prefix, rewritten or already
there, against the files the release ships.

Usage:
    swap = LinkSwap.for_paths(paths)
    result = swap_atbx_links(dest_atbx, swap, shipped, apply=not dry_run)

Rules:
    - Only .xml, .rc and .content members are scanned; every other member keeps its bytes.
    - The rewrite is all or nothing: one missing target or error leaves the archive untouched.
    - Any file: href left outside the new prefix is an error, and so is a non-UNC new prefix
      once at least one link was swapped.
    - A write failure is an error in the result; a member the scan cannot read (corrupt, encrypted)
      raises before anything is written, and the caller reports it.
"""
from __future__ import annotations

import codecs
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple
from urllib.parse import unquote

from conversion.project_model import ProjectPaths

_SCANNED_SUFFIXES = (".xml", ".rc", ".content")
# The href tail: everything up to a quote, backslash (JSON escape), markup character, '#', '?' or whitespace.
_TAIL = r"""[^"'\\<>&#?\s]*"""
_FILE_HREF = re.compile(r"\bfile:/" + _TAIL, re.IGNORECASE)
_UNC_PREFIX = re.compile(r"^file://[^/]", re.IGNORECASE)
_BOMS: Tuple[Tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)


@dataclass(frozen=True)
class LinkSwap:
    """The href prefix a development archive holds and the one the release points at."""

    old_prefix: str
    new_prefix: str

    @classmethod
    def for_paths(cls, paths: ProjectPaths) -> LinkSwap:
        """Prefixes from a project's paths: SOURCE_ROOT -> HELP_ROOT, else DEST_ROOT."""
        target = paths.help_root if paths.help_root is not None else paths.dest_root
        return cls(paths.source_root.as_uri() + "/", target.as_uri() + "/")


@dataclass(frozen=True)
class LinkSwapResult:
    """Outcome of one archive's swap; the archive is rewritten only when ok and swap_count > 0."""

    changed_members: Tuple[str, ...]
    swap_count: int
    missing_targets: Tuple[str, ...]
    errors: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_targets and not self.errors


@dataclass(frozen=True)
class _Text:
    """A decoded member with the encoding and byte-order mark it was read with."""

    text: str
    encoding: str
    bom: bytes

    def encode(self, text: str) -> bytes:
        return self.bom + text.encode(self.encoding)


@dataclass
class _Scan:
    """Accumulated scan state; replaced maps an infolist index to the member's new bytes."""

    replaced: Dict[int, bytes] = field(default_factory=dict)
    changed: List[str] = field(default_factory=list)
    tails: List[str] = field(default_factory=list)
    linked: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _is_scanned(name: str) -> bool:
    return not name.endswith("/") and name.lower().endswith(_SCANNED_SUFFIXES)


def _decode(data: bytes) -> Optional[_Text]:
    """Decode by byte-order mark (UTF-8, UTF-16 LE, UTF-16 BE), else plain UTF-8; None when it fails."""
    bom, encoding = next(((b, e) for b, e in _BOMS if data.startswith(b)), (b"", "utf-8"))
    try:
        return _Text(data[len(bom):].decode(encoding), encoding, bom)
    except UnicodeDecodeError:
        return None


def _swap_text(text: str, pattern: re.Pattern[str], new_prefix: str) -> Tuple[str, List[str]]:
    """Replace each matched prefix with new_prefix, keeping the tail; return the text and the tails."""
    tails: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        tails.append(match.group(1))
        return new_prefix + match.group(1)

    return pattern.sub(_replace, text), tails


def _sort_hrefs(member: str, text: str, new_prefix: str) -> Tuple[List[str], List[str]]:
    """Split the text's file: hrefs: tails of those under new_prefix, and one error per distinct other href."""
    target = new_prefix.casefold()
    linked: List[str] = []
    foreign: Dict[str, None] = {}
    for href in (m.group(0) for m in _FILE_HREF.finditer(text)):
        if href.casefold().startswith(target):
            linked.append(href[len(new_prefix):])
        else:
            foreign[href] = None
    errors = [f"{member}: file: href outside the release prefix {new_prefix}: {href}" for href in foreign]
    return linked, errors


def _scan_member(index: int, info: zipfile.ZipInfo, data: bytes, swap: LinkSwap, scan: _Scan) -> None:
    pattern = re.compile(re.escape(swap.old_prefix) + "(" + _TAIL + ")", re.IGNORECASE)
    decoded = _decode(data)
    if decoded is None:
        scan.errors.append(f"{info.filename}: does not decode as UTF-8 or UTF-16")
        return
    text, tails = _swap_text(decoded.text, pattern, swap.new_prefix)
    if tails:
        scan.replaced[index] = decoded.encode(text)
        scan.changed.append(info.filename)
        scan.tails.extend(tails)
    linked, errors = _sort_hrefs(info.filename, text, swap.new_prefix)
    scan.linked.extend(linked)
    scan.errors.extend(errors)


def _scan_archive(atbx: Path, swap: LinkSwap) -> _Scan:
    scan = _Scan()
    with zipfile.ZipFile(atbx) as zf:
        for index, info in enumerate(zf.infolist()):
            if _is_scanned(info.filename):
                _scan_member(index, info, zf.read(info), swap, scan)
    return scan


def _missing_targets(tails: List[str], shipped: FrozenSet[str]) -> Tuple[str, ...]:
    """Tails (as written) whose URL-decoded path is not shipped, compared ignoring case; each once."""
    shipped_keys = {path.casefold() for path in shipped}
    missing = (tail for tail in tails if unquote(tail).casefold() not in shipped_keys)
    return tuple(dict.fromkeys(missing))


def _target_error(swap: LinkSwap, swap_count: int) -> List[str]:
    if swap_count == 0 or _UNC_PREFIX.match(swap.new_prefix):
        return []
    return [
        f"help links would point at {swap.new_prefix}, which is not a UNC share; "
        "set HELP_ROOT to a UNC share (//server/share/...) in the project .env"
    ]


def _copy_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    fresh = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    fresh.compress_type = info.compress_type
    fresh.external_attr = info.external_attr
    fresh.create_system = info.create_system
    fresh.comment = info.comment
    return fresh


def _copy_members(atbx: Path, temp: Path, replaced: Dict[int, bytes]) -> None:
    """Write every member to temp in infolist order: changed ones re-encoded, the rest as read."""
    with zipfile.ZipFile(atbx) as src, zipfile.ZipFile(temp, "w") as dst:
        dst.comment = src.comment
        for index, info in enumerate(src.infolist()):
            data = replaced[index] if index in replaced else src.read(info)
            dst.writestr(_copy_info(info), data)


def _validate(temp: Path, replaced: Dict[int, bytes]) -> None:
    """Raise unless temp opens, passes testzip and every changed member decodes."""
    with zipfile.ZipFile(temp) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise zipfile.BadZipFile(f"member {bad} fails its CRC check")
        infos = zf.infolist()
        for index in replaced:
            if _decode(zf.read(infos[index])) is None:
                raise zipfile.BadZipFile(f"member {infos[index].filename} does not decode")


def _write_archive(atbx: Path, replaced: Dict[int, bytes]) -> Optional[str]:
    """Rewrite atbx through a validated temp file beside it; an error message when that fails."""
    temp: Optional[Path] = None
    try:
        fd, name = tempfile.mkstemp(prefix=atbx.name + ".", suffix=".tmp", dir=atbx.parent)
        os.close(fd)
        temp = Path(name)
        _copy_members(atbx, temp, replaced)
        _validate(temp, replaced)
        os.replace(temp, atbx)
        temp = None
    except Exception as exc:  # any failure leaves the original archive as it was
        return f"{atbx}: help-link rewrite failed, archive left unchanged: {exc}"
    finally:
        _remove_temp(temp)
    return None


def _remove_temp(temp: Optional[Path]) -> None:
    """Delete a leftover temp archive; a locked file stays rather than masking the result."""
    if temp is None:
        return
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass


def swap_atbx_links(atbx: Path, swap: LinkSwap, shipped: FrozenSet[str], apply: bool) -> LinkSwapResult:
    """Swap the help-link prefix in atbx and check every release-prefix link against the shipped files.

    Args:
        atbx: The copied archive to rewrite in place.
        swap: The old and new href prefixes.
        shipped: Repo-relative posix paths of the files the release ships.
        apply: False reports what would change and never writes.

    Returns:
        The result; the archive is written only when apply is True, swap_count > 0 and it is ok.
    """
    scan = _scan_archive(atbx, swap)
    swap_count = len(scan.tails)
    missing = _missing_targets(scan.linked, shipped)
    errors = scan.errors + _target_error(swap, swap_count)
    if apply and swap_count > 0 and not missing and not errors:
        write_error = _write_archive(atbx, scan.replaced)
        if write_error is not None:
            errors.append(write_error)
    return LinkSwapResult(tuple(scan.changed), swap_count, missing, tuple(errors))
