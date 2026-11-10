"""Tests for conversion.changelog_docx: CHANGELOG.md to a styled Word document."""
from pathlib import Path
from typing import List, Optional

import docx
import pytest
from docx.oxml.ns import qn

from conversion.changelog_docx import (
    CodeBlock,
    Heading,
    ListItem,
    Paragraph,
    Rule,
    convert_file,
    main,
    parse_inline,
    parse_markdown,
    split_identifiers,
)

_FIXTURE = """# Changelog

All notable changes are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

<!-- Add new version entries below this line, newest first -->

---

## [1.2.0] - 2026-11-05

### Overtop Roads

#### Fixed

- The `ot_id` field is now filled; the ZONE_SUBTY value is kept.
- Long item that wraps
  onto a second line with OvertopType.
  - Nested item about fpm.grids.

1. First step
2. Second step with **bold** and *italic* text.

```
python -m conversion.run
```

[1.2.0]: https://example.com/compare/v1.1.0...v1.2.0
"""


def _codes(text: str) -> List[str]:
    return [seg for seg, is_code in split_identifiers(text) if is_code]


@pytest.mark.parametrize(
    "term",
    [
        "ot_id",
        "S_FLD_HAZ_AR",
        "0_2pct",
        "OvertopType",
        "FloodAreaName",
        "areacalcID",
        "fpm.grids",
        "config.json",
        "scripts/fpm/__init__.py",
        "C:\\data\\fpm\\out.gdb",
        "OvertopPolygons_00",
    ],
)
def test_identifier_positives(term: str) -> None:
    assert _codes(f"The {term} value is used.") == [term]


@pytest.mark.parametrize(
    "text",
    [
        "Version 3.17.2 was released on 2026-11-05.",
        "The ArcGIS Pro toolbox and GitHub page.",
        "Zone AH/AO take precedence over A.",
        "FEMA, CSLF, WSE and DEM inputs stay plain.",
        "A 0.2% event, e.g. a 500-year flood, i.e. rare.",
        "The U.S. survey foot and acre-ft units.",
        "Areas of 1,000,000 rows or 500.0 values.",
        "registry/CI synchronization and and/or wording.",
        "The tool ends. Next sentence starts here.",
        "Ask McDonald about the MacBook.",
        "The MacArthur report.",
    ],
)
def test_identifier_negatives(text: str) -> None:
    assert _codes(text) == []


def test_split_identifiers_keeps_surrounding_text() -> None:
    parts = split_identifiers("Use sq_ft here.")
    assert parts == [("Use ", False), ("sq_ft", True), (" here.", False)]


def test_inline_code_and_heuristic_spans() -> None:
    spans = parse_inline("The `ot_id` and FLD_ZONE fields.", {})
    codes = [s.text for s in spans if s.code]
    assert codes == ["ot_id", "FLD_ZONE"]


def test_inline_bold_italic_and_link() -> None:
    spans = parse_inline("**Bold** then *it* and [site](https://x.org).", {})
    assert [(s.text, s.bold, s.italic) for s in spans if s.bold or s.italic] == [("Bold", True, False), ("it", False, True)]
    assert [(s.text, s.url) for s in spans if s.url] == [("site", "https://x.org")]


def test_link_text_is_not_scanned_for_identifiers() -> None:
    spans = parse_inline("[config.json](https://x.org)", {})
    assert [(s.text, s.code, s.url) for s in spans] == [("config.json", False, "https://x.org")]


def test_heading_text_is_not_scanned_for_identifiers() -> None:
    assert not any(s.code for s in parse_inline("ot_id", {}, detect=False))


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("The scripts/fpm/__init__.py file", "scripts/fpm/__init__.py"),
        ("See __init__.py now", "__init__.py"),
        ("Values a__b__c stay", "a__b__c"),
    ],
)
def test_dunder_identifiers_are_code_not_bold(text: str, code: str) -> None:
    spans = parse_inline(text, {})
    assert [s.text for s in spans if s.code] == [code]
    assert not any(s.bold for s in spans)


def test_double_underscore_bold_still_bolds() -> None:
    spans = parse_inline("Use __bold__ here.", {})
    assert [s.text for s in spans if s.bold] == ["bold"]


def test_reference_link_resolves_and_unknown_brackets_stay() -> None:
    spans = parse_inline("[1.2.0] - 2026 [NOT YET IMPLEMENTED]", {"1.2.0": "https://example.com"})
    assert spans[0].text == "1.2.0" and spans[0].url == "https://example.com"
    assert "[NOT YET IMPLEMENTED]" in "".join(s.text for s in spans)


def test_heading_mapping() -> None:
    parsed = parse_markdown("# A\n\n## B\n\n### C\n\n#### D\n")
    assert [(b.level, b.text) for b in parsed.blocks] == [(1, "A"), (2, "B"), (3, "C"), (4, "D")]
    assert all(isinstance(b, Heading) for b in parsed.blocks)


def test_heading_closing_hashes_need_leading_space() -> None:
    parsed = parse_markdown("## Title ##\n\n## C#\n\n### Notes for C#\n")
    assert [b.text for b in parsed.blocks] == ["Title", "C#", "Notes for C#"]


def test_list_nesting_and_continuation() -> None:
    parsed = parse_markdown("- one\n  wrapped\n  - two\n    - three\n- four\n\n1. first\n2. second\n")
    items = [(b.level, b.ordered, b.text) for b in parsed.blocks if isinstance(b, ListItem)]
    assert items == [
        (0, False, "one wrapped"),
        (1, False, "two"),
        (2, False, "three"),
        (0, False, "four"),
        (0, True, "first"),
        (0, True, "second"),
    ]


def test_wrapped_paragraph_lines_join() -> None:
    parsed = parse_markdown("First line\nsecond line\nthird.\n\nNext paragraph.\n")
    assert [b.text for b in parsed.blocks] == ["First line second line third.", "Next paragraph."]


def test_paragraph_after_list_ends_list() -> None:
    parsed = parse_markdown("- a\n  - b\n\nText.\n\n  - c\n")
    assert [type(b) for b in parsed.blocks] == [ListItem, ListItem, Paragraph, ListItem]
    assert parsed.blocks[-1].level == 0


def test_label_line_is_paragraph_and_reference_definition_is_link() -> None:
    parsed = parse_markdown("[BREAKING]: Removed X.\n\n[1.2.0]: https://x/y\n")
    paragraphs = [b for b in parsed.blocks if isinstance(b, Paragraph)]
    assert len(paragraphs) == 1 and "Removed X." in paragraphs[0].text
    assert parsed.links["1.2.0"] == "https://x/y"


def test_block_kinds_comments_and_link_definitions() -> None:
    parsed = parse_markdown(_FIXTURE)
    kinds = {type(b) for b in parsed.blocks}
    assert {Heading, Paragraph, ListItem, Rule, CodeBlock} <= kinds
    assert parsed.links["1.2.0"].startswith("https://example.com")
    assert not any("<!--" in getattr(b, "text", "") for b in parsed.blocks)


@pytest.fixture()
def converted(tmp_path: Path) -> docx.document.Document:
    src = tmp_path / "CHANGELOG.md"
    src.write_text(_FIXTURE, encoding="utf-8")
    out = tmp_path / "CHANGELOG.docx"
    convert_file(src, out, title="Changelog - Test Toolbox")
    assert out.stat().st_size > 0
    return docx.Document(str(out))


def test_end_to_end_heading_styles(converted: docx.document.Document) -> None:
    heads = [(p.style.name, p.text) for p in converted.paragraphs if p.style.name.startswith("Heading")]
    assert heads == [
        ("Heading 1", "Changelog - Test Toolbox"),
        ("Heading 2", "1.2.0 - 2026-11-05"),
        ("Heading 3", "Overtop Roads"),
        ("Heading 4", "Fixed"),
    ]


def test_end_to_end_drops_template_note_and_empty_release(converted: docx.document.Document) -> None:
    text = "\n".join(p.text for p in converted.paragraphs)
    assert "Unreleased" not in text and "Keep a Changelog" not in text
    assert "All notable changes" in text


def test_end_to_end_code_terms_carry_backticks(converted: docx.document.Document) -> None:
    runs = [r for p in converted.paragraphs for r in p.runs if r.font.name == "Consolas"]
    inline = [r.text for r in runs if str(r.font.color.rgb) == "C00000"]
    assert {"`ot_id`", "`ZONE_SUBTY`", "`OvertopType`", "`fpm.grids`"} <= set(inline)
    assert all(t.startswith("`") and t.endswith("`") for t in inline)


def test_end_to_end_list_styles(converted: docx.document.Document) -> None:
    styles = [p.style.name for p in converted.paragraphs if p.style.name.startswith("List")]
    assert styles == ["List Bullet", "List Bullet", "List Bullet 2", "List Number", "List Number"]


def test_end_to_end_heading_link_is_external_hyperlink(converted: docx.document.Document) -> None:
    heading = next(p for p in converted.paragraphs if p.style.name == "Heading 2")
    links = heading._p.findall(qn("w:hyperlink"))
    assert len(links) == 1
    rel = converted.part.rels[links[0].get(qn("r:id"))]
    assert rel.is_external and rel.target_ref == "https://example.com/compare/v1.1.0...v1.2.0"


def _pr_children(paragraph) -> List[str]:
    return [child.tag.split("}")[1] for child in paragraph._p.pPr]


def _write(tmp_path: Path, text: str) -> Path:
    src = tmp_path / "in.md"
    src.write_text(text, encoding="utf-8")
    return src


def _num_ids(path: Path, style: str) -> List[Optional[int]]:
    paras = [p for p in docx.Document(str(path)).paragraphs if p.style.name == style]
    return [p._p.pPr.numPr.numId.val if p._p.pPr.numPr is not None else None for p in paras]


def test_code_block_is_one_shaded_paragraph(tmp_path: Path) -> None:
    out = convert_file(_write(tmp_path, "```\nline one\nline two\n```\n"), tmp_path / "c.docx")
    para = docx.Document(str(out)).paragraphs[0]
    assert para.text == "line one\nline two"
    assert _pr_children(para)[:1] == ["shd"] and {"spacing", "ind"} <= set(_pr_children(para))
    assert all(r.font.name == "Consolas" for r in para.runs)


def test_numbered_lists_restart(tmp_path: Path) -> None:
    out = convert_file(_write(tmp_path, "1. a\n2. b\n\nText.\n\n1. c\n"), tmp_path / "n.docx")
    ids = _num_ids(out, "List Number")
    assert ids[0] is not None and ids[1] == ids[0] and ids[2] not in (None, ids[0])


def test_numbered_list_after_text_and_bullets_restarts(tmp_path: Path) -> None:
    out = convert_file(_write(tmp_path, "1. a\n\nText.\n\n- b\n  - c\n1. d\n"), tmp_path / "n.docx")
    ids = _num_ids(out, "List Number")
    assert len(ids) == 2 and None not in ids and ids[1] != ids[0]


def test_numbered_list_nested_in_bullets_restarts(tmp_path: Path) -> None:
    out = convert_file(_write(tmp_path, "- x\n  1. a\n  2. b\n- y\n  1. c\n"), tmp_path / "n.docx")
    ids = _num_ids(out, "List Number 2")
    assert ids[0] is not None and ids[1] == ids[0] and ids[2] not in (None, ids[0])


def test_repeated_rules_collapse_to_one(tmp_path: Path) -> None:
    out = convert_file(_write(tmp_path, "# T\n\n---\n\n---\n\nText.\n"), tmp_path / "r.docx")
    paras = docx.Document(str(out)).paragraphs
    assert sum(1 for p in paras if p._p.pPr is not None and p._p.pPr.find(qn("w:pBdr")) is not None) == 1


def test_cli_writes_docx(tmp_path: Path) -> None:
    src = _write(tmp_path, "# T\n\n- `a_b`\n")
    out = tmp_path / "out.docx"
    assert main([str(src), str(out), "--title", "Changelog - CLI"]) == 0
    assert out.stat().st_size > 0
    heads = [p.text for p in docx.Document(str(out)).paragraphs if p.style.name == "Heading 1"]
    assert heads == ["Changelog - CLI"]
