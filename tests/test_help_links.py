"""Tests for conversion.help_links: the help-link prefix swap inside a copied .atbx archive."""
import codecs
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

import pytest

from conversion.help_links import LinkSwap, LinkSwapResult, swap_atbx_links
from conversion.project_model import ProjectPaths

_PAGE = "tool_metadata/tool_help/smooth_simplify.html"
_GONE = "tool_metadata/tool_help/gone.html"
_SHIPPED: FrozenSet[str] = frozenset({_PAGE, "scripts/fpm/__init__.py"})
_HELP_ROOT = Path("//srv/share/fpm_releases/FPM_1_0_0")
_STAMP = (2024, 5, 6, 7, 8, 10)
_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
_TOOL = "SmoothAndSimplifyPolygons.tool/"
_CONTENT = _TOOL + "tool.content"
_XML = _TOOL + "tool.metadata.xml"
_RC = _TOOL + "tool.content.rc"
_IMG = _TOOL + "illustration.png"
_SCRIPT = _TOOL + "tool.script.execute.py"
_BOMS = {
    "utf-8-sig": codecs.BOM_UTF8,
    "utf-16-le": codecs.BOM_UTF16_LE,
    "utf-16-be": codecs.BOM_UTF16_BE,
}


@dataclass(frozen=True)
class _Roots:
    """One test's source checkout, dest copy, archive folder and swap (UNC help root)."""

    src: Path
    dst: Path
    box: Path
    swap: LinkSwap

    @property
    def atbx(self) -> Path:
        return self.box / "floodplain_mapping.atbx"

    def href(self, tail: str = _PAGE, prefix: Optional[str] = None) -> str:
        return (self.swap.old_prefix if prefix is None else prefix) + tail

    def new_href(self, tail: str = _PAGE) -> str:
        return self.swap.new_prefix + tail


@pytest.fixture
def roots(tmp_path: Path) -> _Roots:
    src, dst, box = tmp_path / "src", tmp_path / "dst", tmp_path / "box"
    for folder in (src, dst, box):
        folder.mkdir()
    swap = LinkSwap.for_paths(ProjectPaths(src, dst, help_root=_HELP_ROOT))
    return _Roots(src, dst, box, swap)


# --- archive helpers ---------------------------------------------------------------------------------------

def _encode(text: str, encoding: str) -> bytes:
    """Encode text; the UTF-16 forms get their byte-order mark, utf-8-sig adds its own."""
    if encoding in ("utf-16-le", "utf-16-be"):
        return _BOMS[encoding] + text.encode(encoding)
    return text.encode(encoding)


def _decode(data: bytes) -> str:
    for encoding, bom in _BOMS.items():
        if data.startswith(bom):
            return data[len(bom):].decode(encoding.replace("-sig", ""))
    return data.decode("utf-8")


def _xml(*hrefs: str, prose: str = "") -> bytes:
    """A tool.metadata.xml whose usage holds the prose and one escaped anchor per href, as Pro stores HTML."""
    anchors = "".join(f"&lt;A HREF=&quot;{href}&quot;&gt;link&lt;/A&gt;" for href in hrefs)
    return f'<?xml version="1.0"?>\n<metadata><tool><usage>{prose}{anchors}</usage></tool></metadata>'.encode()


def _rc(*hrefs: str, encoding: str = "utf-8-sig") -> bytes:
    """A tool.content.rc whose usage holds one anchor per href, JSON-escaped as Pro writes it."""
    anchors = "".join(f'<a href="{href}">Full Tool Help</a>' for href in hrefs)
    return _encode(json.dumps({"map": {"usage": anchors}}, indent=1), encoding)


def _content(*hrefs: str) -> bytes:
    """A plain UTF-8 tool.content whose description holds one anchor per href."""
    anchors = "".join(f'<a href="{href}">Help</a>' for href in hrefs)
    return json.dumps({"type": "ScriptTool", "description": anchors}).encode()


def _script(href: str) -> bytes:
    """An embedded tool script whose text holds the href; scripts are never scanned."""
    return f"HELP_PAGE = {href!r}\n".encode()


def _build(atbx: Path, members: List[Tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(atbx, "w") as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=_STAMP)
            stored = name.endswith(("/", ".png"))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            zf.writestr(info, data)


def _standard(roots: _Roots, rc_encoding: str = "utf-8-sig") -> List[Tuple[str, bytes]]:
    """Directory entry; linked tool.content, xml and rc; a png and a script holding the prefix text."""
    return [
        (_TOOL, b""),
        (_CONTENT, _content(roots.href())),
        (_XML, _xml(roots.href())),
        (_RC, _rc(roots.href(), encoding=rc_encoding)),
        (_IMG, _PNG + roots.href().encode("ascii")),
        (_SCRIPT, _script(roots.href())),
    ]


def _read(atbx: Path) -> Dict[str, bytes]:
    with zipfile.ZipFile(atbx) as zf:
        return {info.filename: zf.read(info) for info in zf.infolist()}


def _layout(atbx: Path) -> List[Tuple[str, int, Tuple[int, ...]]]:
    with zipfile.ZipFile(atbx) as zf:
        return [(i.filename, i.compress_type, i.date_time) for i in zf.infolist()]


def _swap(
    roots: _Roots,
    apply: bool = True,
    shipped: FrozenSet[str] = _SHIPPED,
    swap: Optional[LinkSwap] = None,
) -> LinkSwapResult:
    return swap_atbx_links(roots.atbx, swap or roots.swap, shipped, apply=apply)


def _local_swap(roots: _Roots) -> LinkSwap:
    """The swap without HELP_ROOT: links would point at the local (drive-letter) dest_root."""
    return LinkSwap.for_paths(ProjectPaths(roots.src, roots.dst))


def _assert_untouched(roots: _Roots, before: bytes) -> None:
    """The archive keeps its bytes and its folder holds no temp file."""
    assert roots.atbx.read_bytes() == before
    assert sorted(os.listdir(roots.box)) == [roots.atbx.name]


# --- prefixes ----------------------------------------------------------------------------------------------

def test_prefixes_without_help_root(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    swap = LinkSwap.for_paths(ProjectPaths(src, dst))
    assert swap.old_prefix == src.as_uri() + "/"
    assert swap.new_prefix == dst.as_uri() + "/"


def test_help_root_replaces_dest_root_in_links(tmp_path):
    swap = LinkSwap.for_paths(ProjectPaths(tmp_path / "src", tmp_path / "dst", help_root=_HELP_ROOT))
    assert swap.new_prefix == _HELP_ROOT.as_uri() + "/"


# --- the swap ----------------------------------------------------------------------------------------------

def test_swap_count_and_tail_kept(roots):
    _build(roots.atbx, _standard(roots))
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 3
    assert result.changed_members == (_CONTENT, _XML, _RC)
    members = _read(roots.atbx)
    assert members[_CONTENT] == _content(roots.new_href())
    assert members[_XML] == _xml(roots.new_href())
    assert members[_RC] == _rc(roots.new_href())


def test_prefix_match_ignores_case(roots):
    lower, upper = roots.swap.old_prefix.lower(), roots.swap.old_prefix.upper()
    _build(roots.atbx, [(_XML, _xml(roots.href(prefix=lower))), (_RC, _rc(roots.href(prefix=upper)))])
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 2
    members = _read(roots.atbx)
    assert members[_XML] == _xml(roots.new_href())
    assert members[_RC] == _rc(roots.new_href())


@pytest.mark.parametrize("encoding", sorted(_BOMS))
def test_byte_order_mark_is_kept(roots, encoding):
    _build(roots.atbx, _standard(roots, rc_encoding=encoding))
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    members = _read(roots.atbx)
    assert members[_RC] == _rc(roots.new_href(), encoding=encoding)
    assert members[_XML] == _xml(roots.new_href())


def test_unscanned_members_are_byte_identical(roots):
    members = dict(_standard(roots))
    _build(roots.atbx, list(members.items()))
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    after = _read(roots.atbx)
    assert after[_IMG] == members[_IMG]
    assert after[_SCRIPT] == members[_SCRIPT]


def test_anchor_and_http_hrefs_are_left_alone(roots):
    others = ("#parameters", "https://example.com/help", "http://example.com/x.html")
    _build(roots.atbx, [(_XML, _xml(*others, roots.href()))])
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 1
    assert _read(roots.atbx)[_XML] == _xml(*others, roots.new_href())


def test_prose_file_colon_is_not_a_link(roots):
    prose = "Output file: name of the cleaned feature class. "
    _build(roots.atbx, [(_XML, _xml(roots.href(), prose=prose))])
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert _read(roots.atbx)[_XML] == _xml(roots.new_href(), prose=prose)


def test_url_encoded_tail_is_decoded_for_the_check(roots):
    tail = "tool_metadata/tool_help/two%20words.html"
    _build(roots.atbx, [(_XML, _xml(roots.href(tail)))])
    result = _swap(roots, shipped=frozenset({"tool_metadata/tool_help/two words.html"}))
    assert result.ok, (result.missing_targets, result.errors)
    assert _read(roots.atbx)[_XML] == _xml(roots.new_href(tail))


def test_tail_check_ignores_case(roots):
    tail = "tool_metadata/Tool_Help/Smooth_Simplify.html"
    _build(roots.atbx, [(_XML, _xml(roots.href(tail)))])
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert _read(roots.atbx)[_XML] == _xml(roots.new_href(tail))


def test_member_order_compression_and_timestamps_are_kept(roots):
    _build(roots.atbx, _standard(roots))
    before = _layout(roots.atbx)
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert _layout(roots.atbx) == before
    with zipfile.ZipFile(roots.atbx) as zf:
        assert zf.testzip() is None
    assert sorted(os.listdir(roots.box)) == [roots.atbx.name]


# --- refusals: nothing written -----------------------------------------------------------------------------

def test_missing_target_writes_nothing(roots):
    _build(roots.atbx, [(_XML, _xml(roots.href(_GONE))), (_RC, _rc(roots.href()))])
    before = roots.atbx.read_bytes()
    result = _swap(roots)
    assert not result.ok
    assert _GONE in result.missing_targets
    _assert_untouched(roots, before)


def test_page_on_disk_but_not_shipped_is_missing(roots):
    for root in (roots.src, roots.dst):
        page = root / _PAGE
        page.parent.mkdir(parents=True)
        page.write_text("<html></html>\n", encoding="utf-8")
    _build(roots.atbx, [(_XML, _xml(roots.href()))])
    before = roots.atbx.read_bytes()
    result = _swap(roots, shipped=frozenset())
    assert not result.ok
    assert result.missing_targets == (_PAGE,)
    _assert_untouched(roots, before)


def test_each_missing_tail_is_reported_once(roots):
    lost = "tool_metadata/tool_help/lost.html"
    xml = _xml(roots.href(_GONE), roots.href(_GONE))
    _build(roots.atbx, [(_XML, xml), (_RC, _rc(roots.href(_GONE), roots.href(lost)))])
    result = _swap(roots)
    assert sorted(result.missing_targets) == sorted([_GONE, lost])


def test_link_already_at_the_release_prefix_is_checked(roots):
    _build(roots.atbx, [(_XML, _xml(roots.new_href(_GONE))), (_RC, _rc(roots.href()))])
    before = roots.atbx.read_bytes()
    result = _swap(roots)
    assert not result.ok
    assert result.missing_targets == (_GONE,)
    assert result.swap_count == 1
    _assert_untouched(roots, before)


def test_shipped_link_already_at_the_release_prefix_is_ok(roots):
    _build(roots.atbx, [(_XML, _xml(roots.new_href())), (_RC, _rc(roots.href()))])
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 1
    assert result.changed_members == (_RC,)


def test_leftover_drive_href_is_an_error(roots):
    foreign = "file:///Z:/elsewhere/page.html"
    _build(roots.atbx, [(_XML, _xml(foreign, roots.href()))])
    before = roots.atbx.read_bytes()
    result = _swap(roots)
    assert not result.ok
    assert any(foreign in error for error in result.errors), result.errors
    _assert_untouched(roots, before)


def test_lone_lowercase_drive_href_is_an_error(roots):
    foreign = "file:///z:/x.html"
    _build(roots.atbx, [(_RC, _rc(foreign))])
    before = roots.atbx.read_bytes()
    result = _swap(roots)
    assert not result.ok
    assert result.swap_count == 0
    assert any(foreign in error for error in result.errors), result.errors
    _assert_untouched(roots, before)


def test_foreign_unc_href_is_an_error(roots):
    foreign = "file://other/share/x.html"
    _build(roots.atbx, [(_XML, _xml(foreign, roots.href()))])
    before = roots.atbx.read_bytes()
    result = _swap(roots)
    assert not result.ok
    assert any(foreign in error for error in result.errors), result.errors
    _assert_untouched(roots, before)


def test_local_target_with_links_is_one_error(roots):
    _build(roots.atbx, _standard(roots))
    before = roots.atbx.read_bytes()
    result = _swap(roots, swap=_local_swap(roots))
    assert result.swap_count == 3
    assert result.missing_targets == ()
    assert len(result.errors) == 1, result.errors
    assert "HELP_ROOT" in result.errors[0]
    _assert_untouched(roots, before)


def test_local_target_without_links_is_ok(roots):
    _build(roots.atbx, [(_CONTENT, _content()), (_XML, _xml("https://example.com/help"))])
    result = _swap(roots, swap=_local_swap(roots))
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 0


@pytest.mark.skipif(os.name != "nt", reason="only Windows refuses os.replace onto a read-only file")
def test_read_only_archive_leaves_no_temp_file(roots):
    _build(roots.atbx, _standard(roots))
    before = roots.atbx.read_bytes()
    os.chmod(roots.atbx, stat.S_IREAD)
    try:
        result = _swap(roots)
    finally:
        os.chmod(roots.atbx, stat.S_IREAD | stat.S_IWRITE)
    assert not result.ok
    assert result.errors
    _assert_untouched(roots, before)


def test_failed_validation_leaves_no_temp_file(roots, monkeypatch):
    _build(roots.atbx, _standard(roots))
    before = roots.atbx.read_bytes()
    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: _RC)
    result = _swap(roots)
    assert not result.ok
    assert result.errors
    _assert_untouched(roots, before)


# --- dry run and no match ----------------------------------------------------------------------------------

def test_dry_run_reports_and_writes_nothing(roots):
    _build(roots.atbx, _standard(roots))
    before = roots.atbx.read_bytes()
    result = _swap(roots, apply=False)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 3
    assert result.changed_members == (_CONTENT, _XML, _RC)
    _assert_untouched(roots, before)


def test_archive_without_links_is_not_rewritten(roots):
    _build(roots.atbx, [(_CONTENT, _content()), (_XML, _xml("https://example.com/help"))])
    os.utime(roots.atbx, (1_000_000_000, 1_000_000_000))
    result = _swap(roots)
    assert result.ok, (result.missing_targets, result.errors)
    assert result.swap_count == 0
    assert result.changed_members == ()
    assert roots.atbx.stat().st_mtime == 1_000_000_000
