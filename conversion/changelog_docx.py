"""CHANGELOG.md to a styled Word document for toolbox end users.

The look follows the release changelog the developer formatted by hand: Calibri headings in a blue
ramp, Aptos 10 pt body text, a light blue rule between releases, and code-like terms in dark red
Consolas wrapped in visible backticks. Headings use the built-in Heading 1-6 styles (levels 5 and 6
share the level-4 look), so the Word navigation pane lists every release, tool and change type.

Usage:
    python -m conversion.changelog_docx CHANGELOG.md CHANGELOG.docx [--title "Changelog - FPM"]

Rules:
    - Markdown covered: ATX headings, bullet and numbered lists (nested by indent, wrapped lines
      joined), paragraphs, horizontal rules, fenced code blocks, inline code, bold, italic, inline
      links, reference links and link definitions. HTML comments outside fenced code are dropped.
    - Terms in backticks render as code; plain text is also scanned for identifiers (see
      IDENTIFIER_RULES). Headings and link text are not scanned.
    - Release sections with no content (an empty Unreleased) and paragraphs matching
      DROP_PARAGRAPH_PATTERNS (the Keep a Changelog note) are left out; repeated rules collapse.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import docx
from docx.document import Document as DocxDocument
from docx.enum.text import WD_UNDERLINE
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph as DocxParagraph

# ---------------------------------------------------------------------------------------------
# Identifier heuristic (tune here)
# ---------------------------------------------------------------------------------------------

FILE_EXTENSIONS: Tuple[str, ...] = (
    "py", "pyt", "json", "md", "txt", "xml", "html", "toml", "yaml", "yml", "ini", "cfg", "log",
    "csv", "xlsx", "docx", "pdf", "zip", "atbx", "tbx", "aprx", "lyrx", "gdb", "gpkg", "shp", "tif",
    "tiff", "vrt", "img", "sde",
)
_EXT = "(?:" + "|".join(FILE_EXTENSIONS) + ")"

# Each rule is a full-match pattern over one token; a token matching any rule renders as code.
IDENTIFIER_RULES: Tuple[Tuple[str, str], ...] = (
    ("drive_path", r"[A-Za-z]:[\\/][^\s]*"),
    ("deep_path", r"(?=.*[a-z_])[\w.\-]*(?:[\\/][\w.\-<>]+){2,}[\\/]?"),
    ("file_name", r"(?:[\w.\-]+[\\/])*[\w\-]+(?:\.[\w\-]+)*\." + _EXT),
    ("dotted_name", r"[A-Za-z_]\w+(?:\.[A-Za-z_]\w+)+"),
    ("snake_case", r"(?=.*[A-Za-z])_*[A-Za-z0-9]+(?:_+[A-Za-z0-9<>]+)+_*"),
    ("camel_case", r"[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*"),
    ("pascal_case", r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+(?:[A-Z]+[a-z0-9]*)?"),
)
_RULES = tuple((name, re.compile(pattern)) for name, pattern in IDENTIFIER_RULES)

# Product and personal names that look like identifiers but read as English.
IDENTIFIER_DENY: Tuple[str, ...] = (
    "ArcGIS", "GitHub", "GitLab", "JavaScript", "TypeScript", "PowerShell", "PowerPoint", "SharePoint",
    "OneDrive", "YouTube", "LinkedIn", "iOS", "macOS", "iPhone", "iPad", "eBay", "pH",
)
IDENTIFIER_DENY_PATTERNS: Tuple[str, ...] = (r"Ma?c[A-Z][a-z]+",)
_DENY = frozenset(IDENTIFIER_DENY)
_DENY_RES = tuple(re.compile(p) for p in IDENTIFIER_DENY_PATTERNS)

# Candidate tokens: runs without whitespace or list/sentence punctuation; edges trimmed below.
_TOKEN = re.compile(r"""[^\s(),;"]+""")
_LEAD_TRIM = "'["
_TAIL_TRIM = ".:'!?]"

# Paragraphs left out of the end-user document (maintainer notes).
DROP_PARAGRAPH_PATTERNS: Tuple[str, ...] = (r"^The format is based on \[Keep a Changelog\]",)
_DROP_RES = tuple(re.compile(p) for p in DROP_PARAGRAPH_PATTERNS)

# ---------------------------------------------------------------------------------------------
# Look (lifted from the hand-formatted example)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadingLook:
    """Font, size (pt), color and spacing (pt) of one heading level."""

    font: str
    size: float
    color: str
    before: float
    after: float


HEADING_LOOKS: Dict[int, HeadingLook] = {
    1: HeadingLook("Calibri", 20, "1F4E79", 0, 4),
    2: HeadingLook("Calibri", 16, "1F4E79", 10, 4),
    3: HeadingLook("Calibri", 13, "2F5597", 10, 4),
    4: HeadingLook("Calibri", 11, "4472C4", 10, 4),
}
BODY_FONT, BODY_SIZE, BODY_COLOR, BODY_AFTER, BODY_LINE = "Aptos", 10, "000000", 5, 1.16
CODE_FONT, CODE_SIZE, CODE_COLOR = "Consolas", 9, "C00000"
BLOCK_COLOR, BLOCK_FILL = "1F1F1F", "F2F2F2"
LINK_COLOR = "0563C1"
RULE_COLOR, RULE_SIZE = "B4C6E7", 6
BULLET_STYLES = ("List Bullet", "List Bullet 2", "List Bullet 3")
NUMBER_STYLES = ("List Number", "List Number 2", "List Number 3")

# ---------------------------------------------------------------------------------------------
# Block model and parser
# ---------------------------------------------------------------------------------------------


@dataclass
class Heading:
    """An ATX heading (# to ######)."""

    level: int
    text: str


@dataclass
class Paragraph:
    """A paragraph; wrapped source lines joined with single spaces."""

    text: str


@dataclass
class ListItem:
    """One list item at a nesting level (0 = top)."""

    level: int
    ordered: bool
    text: str


@dataclass
class CodeBlock:
    """A fenced code block, kept verbatim."""

    text: str


@dataclass
class Rule:
    """A horizontal rule."""


Block = Union[Heading, Paragraph, ListItem, CodeBlock, Rule]


@dataclass
class ParsedMarkdown:
    """Blocks in source order plus link definitions keyed by lower-cased label."""

    blocks: List[Block] = field(default_factory=list)
    links: Dict[str, str] = field(default_factory=dict)


# A closing run of '#' counts only after whitespace, so 'Notes for C#' keeps its '#'.
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*(?:(?<=\s)#+)?\s*$")
_RULE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# A full reference definition: label, destination and an optional title, nothing else on the line.
_LINK_DEF = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _in_comment(chunk: List[str]) -> bool:
    """True when the joined lines leave an HTML comment open."""
    return "<!--" in _COMMENT.sub("", "".join(chunk))


def _strip_comments(text: str) -> str:
    """Remove HTML comments outside fenced code blocks; fence bodies stay verbatim."""
    out: List[str] = []
    chunk: List[str] = []
    marker: Optional[str] = None
    for line in text.splitlines(keepends=True):
        fence = _FENCE.match(line) if marker is None else None
        if marker is not None:
            out.append(line)
            marker = None if line.strip().startswith(marker) else marker
        elif fence and not _in_comment(chunk):
            out.extend((_COMMENT.sub("", "".join(chunk)), line))
            chunk, marker = [], fence.group(1)
        else:
            chunk.append(line)
    out.append(_COMMENT.sub("", "".join(chunk)))
    return "".join(out)


class _Parser:
    """Line-driven block parser for the Markdown subset changelogs use."""

    def __init__(self, text: str) -> None:
        self.lines = _strip_comments(text).splitlines()
        self.pos = 0
        self.out = ParsedMarkdown()
        self.para: List[str] = []
        self.item: Optional[ListItem] = None
        self.indents: List[int] = []

    def run(self) -> ParsedMarkdown:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            self.pos += 1
            self._line(line)
        self._flush()
        return self.out

    def _line(self, line: str) -> None:
        if not line.strip():
            self._flush()
        elif _FENCE.match(line):
            self._fence(_FENCE.match(line).group(1))
        elif _HEADING.match(line):
            self._end_list()
            m = _HEADING.match(line)
            self.out.blocks.append(Heading(len(m.group(1)), m.group(2)))
        elif _RULE.match(line):
            self._end_list()
            self.out.blocks.append(Rule())
        else:
            self._text_line(line)

    def _text_line(self, line: str) -> None:
        def_match = _LINK_DEF.match(line)
        item_match = _ITEM.match(line)
        if def_match and not self.para:
            self._flush()
            self.out.links[def_match.group(1).lower()] = def_match.group(2)
        elif item_match:
            self._start_item(item_match)
        elif self.item is not None:
            self.item.text += " " + line.strip()
        else:
            if self.indents:
                self._end_list()
            self.para.append(line.strip())

    def _start_item(self, m: re.Match) -> None:
        self._flush_para()
        indent = len(m.group(1).expandtabs(4))
        while self.indents and self.indents[-1] > indent:
            self.indents.pop()
        if not self.indents or self.indents[-1] < indent:
            self.indents.append(indent)
        level = min(len(self.indents) - 1, len(BULLET_STYLES) - 1)
        self.item = ListItem(level, m.group(2)[0].isdigit(), m.group(3).strip())
        self.out.blocks.append(self.item)

    def _fence(self, marker: str) -> None:
        self._end_list()
        body: List[str] = []
        while self.pos < len(self.lines) and not self.lines[self.pos].strip().startswith(marker):
            body.append(self.lines[self.pos])
            self.pos += 1
        self.pos += 1
        self.out.blocks.append(CodeBlock("\n".join(body)))

    def _flush_para(self) -> None:
        if self.para:
            self.out.blocks.append(Paragraph(" ".join(self.para)))
            self.para = []

    def _flush(self) -> None:
        """Blank line: end the paragraph; a list stays open until other content arrives."""
        self._flush_para()
        self.item = None

    def _end_list(self) -> None:
        self._flush()
        self.indents = []


def parse_markdown(text: str) -> ParsedMarkdown:
    """Parse Markdown text into blocks and link definitions."""
    return _Parser(text).run()


# ---------------------------------------------------------------------------------------------
# Identifier detection and inline spans
# ---------------------------------------------------------------------------------------------


def is_identifier(token: str) -> bool:
    """True when a trimmed token matches an identifier rule and no deny entry."""
    if token in _DENY or any(p.fullmatch(token) for p in _DENY_RES):
        return False
    return any(rule.fullmatch(token) for _, rule in _RULES)


def _trimmed(start: int, token: str) -> Tuple[int, str]:
    """Strip leading quotes/brackets and trailing sentence punctuation; return new start and token."""
    stripped = token.lstrip(_LEAD_TRIM)
    start += len(token) - len(stripped)
    return start, stripped.rstrip(_TAIL_TRIM)


def split_identifiers(text: str) -> List[Tuple[str, bool]]:
    """Split plain text into (segment, is_code) pairs; code segments are detected identifiers."""
    parts: List[Tuple[str, bool]] = []
    cursor = 0
    for m in _TOKEN.finditer(text):
        start, token = _trimmed(m.start(), m.group(0))
        if not token or not is_identifier(token):
            continue
        if start > cursor:
            parts.append((text[cursor:start], False))
        parts.append((token, True))
        cursor = start + len(token)
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return parts


@dataclass
class Span:
    """A run of inline text with its formatting."""

    text: str
    code: bool = False
    bold: bool = False
    italic: bool = False
    url: Optional[str] = None


_INLINE = re.compile(
    r"(?P<esc>\\[\\`*_\[\]()#+\-.!<>])"
    r"|`(?P<code>[^`]+)`"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>(?:[^()\s]|\([^()\s]*\))+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
    r"|\[(?P<rtext>[^\]]+)\](?:\[(?P<rref>[^\]]*)\])?"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|(?<![\w/\\.])__(?P<ubold>[^\s_](?:.*?[^\s_])?)__(?![\w.])"
    r"|\*(?P<ital>[^\s*](?:.*?[^\s*])?)\*"
    r"|(?<!\w)_(?P<uital>[^\s_](?:.*?[^\s_])?)_(?!\w)"
)


@dataclass(frozen=True)
class _Ctx:
    """Inline parsing context: link definitions, identifier detection, inherited emphasis."""

    links: Dict[str, str]
    detect: bool
    bold: bool = False
    italic: bool = False


def _plain(text: str, ctx: _Ctx) -> List[Span]:
    pieces = split_identifiers(text) if ctx.detect else [(text, False)]
    return [Span(t, code=c, bold=ctx.bold, italic=ctx.italic) for t, c in pieces if t]


def _linked(text: str, url: str, ctx: _Ctx) -> List[Span]:
    """Inline-parse link text (no identifier scan) and point every span at url."""
    spans = _spans(text, _Ctx(ctx.links, False, ctx.bold, ctx.italic))
    for span in spans:
        span.url = url
    return spans


def _bracketed(m: re.Match, ctx: _Ctx) -> List[Span]:
    """Unresolved reference: inline-parse the text and keep the literal brackets around it."""
    tail = m.group(0)[len(m.group("rtext")) + 2:]
    open_span = Span("[", bold=ctx.bold, italic=ctx.italic)
    close_span = Span("]" + tail, bold=ctx.bold, italic=ctx.italic)
    return [open_span] + _spans(m.group("rtext"), ctx) + [close_span]


def _ref_link(m: re.Match, ctx: _Ctx) -> List[Span]:
    label = (m.group("rref") or m.group("rtext")).lower()
    url = ctx.links.get(label)
    if url is None:
        return _bracketed(m, ctx)
    return _linked(m.group("rtext"), url, ctx)


def _emphasis(m: re.Match, ctx: _Ctx) -> List[Span]:
    if m.group("bold") or m.group("ubold"):
        inner = _Ctx(ctx.links, ctx.detect, True, ctx.italic)
        return _spans(m.group("bold") or m.group("ubold"), inner)
    inner = _Ctx(ctx.links, ctx.detect, ctx.bold, True)
    return _spans(m.group("ital") or m.group("uital"), inner)


def _token(m: re.Match, ctx: _Ctx) -> List[Span]:
    if m.group("esc"):
        return [Span(m.group("esc")[1], bold=ctx.bold, italic=ctx.italic)]
    if m.group("code"):
        return [Span(m.group("code"), code=True, bold=ctx.bold, italic=ctx.italic)]
    if m.group("ltext"):
        return _linked(m.group("ltext"), m.group("lurl"), ctx)
    if m.group("rtext"):
        return _ref_link(m, ctx)
    return _emphasis(m, ctx)


def _spans(text: str, ctx: _Ctx) -> List[Span]:
    spans: List[Span] = []
    cursor = 0
    for m in _INLINE.finditer(text):
        spans.extend(_plain(text[cursor:m.start()], ctx))
        spans.extend(_token(m, ctx))
        cursor = m.end()
    spans.extend(_plain(text[cursor:], ctx))
    return spans


def parse_inline(text: str, links: Dict[str, str], detect: bool = True) -> List[Span]:
    """Parse inline Markdown into spans; detect=True also marks unmarked identifiers as code."""
    return _spans(text, _Ctx(links, detect))


# ---------------------------------------------------------------------------------------------
# Block filtering
# ---------------------------------------------------------------------------------------------


def _section_is_empty(blocks: Sequence[Block], index: int) -> bool:
    """True when the heading at index holds only rules and deeper headings before the next heading
    at its level or above."""
    level = blocks[index].level
    for block in blocks[index + 1:]:
        if isinstance(block, Heading):
            if block.level <= level:
                return True
        elif not isinstance(block, Rule):
            return False
    return True


def _drop_paragraph(block: Block) -> bool:
    return isinstance(block, Paragraph) and any(p.search(block.text) for p in _DROP_RES)


def filter_blocks(blocks: Sequence[Block]) -> List[Block]:
    """Drop empty release sections (with their empty subheadings) and maintainer notes, then
    collapse repeated rules."""
    kept: List[Block] = []
    skipping = False
    for i, block in enumerate(blocks):
        if isinstance(block, Heading) and block.level <= 2:
            skipping = block.level == 2 and _section_is_empty(blocks, i)
        if (skipping and isinstance(block, Heading)) or _drop_paragraph(block):
            continue
        if isinstance(block, Rule) and kept and isinstance(kept[-1], Rule):
            continue
        kept.append(block)
    return kept


# ---------------------------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------------------------


def _set_fonts(rpr, name: str) -> None:
    """Point every script slot of an rPr at one font and drop theme-font overrides."""
    fonts = rpr.get_or_add_rFonts()
    for slot in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{slot}"), name)
    for slot in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn(f"w:{slot}"), None)


def _apply_font(font, rpr, name: str, size: float, color: str) -> None:
    _set_fonts(rpr, name)
    font.size = Pt(size)
    font.color.rgb = RGBColor.from_string(color)


def _style_heading(document: DocxDocument, level: int, look: HeadingLook) -> None:
    style = document.styles[f"Heading {level}"]
    _apply_font(style.font, style.element.get_or_add_rPr(), look.font, look.size, look.color)
    style.font.bold = False
    style.font.italic = False
    style.paragraph_format.space_before = Pt(look.before)
    style.paragraph_format.space_after = Pt(look.after)


def _style_body(document: DocxDocument) -> None:
    """Body font and spacing; list items of one list sit tight (contextual spacing), as in the example."""
    style = document.styles["Normal"]
    _apply_font(style.font, style.element.get_or_add_rPr(), BODY_FONT, BODY_SIZE, BODY_COLOR)
    style.paragraph_format.space_after = Pt(BODY_AFTER)
    style.paragraph_format.line_spacing = BODY_LINE
    for name in BULLET_STYLES + NUMBER_STYLES:
        ppr = document.styles[name].element.get_or_add_pPr()
        if ppr.find(qn("w:contextualSpacing")) is None:
            ppr.append(OxmlElement("w:contextualSpacing"))


def _setup_document(title: str) -> DocxDocument:
    document = docx.Document()
    _style_body(document)
    for level in range(1, 7):
        _style_heading(document, level, HEADING_LOOKS[min(level, 4)])
    for section in document.sections:
        section.left_margin = section.right_margin = Inches(1)
        section.top_margin = section.bottom_margin = Inches(1)
    props = document.core_properties
    props.title, props.author, props.last_modified_by, props.comments = title, "", "", ""
    return document


def _format_run(run, span: Span, in_heading: bool) -> None:
    run.bold = span.bold or (span.url is not None and in_heading) or None
    run.italic = span.italic or None
    if span.code:
        _apply_font(run.font, run.element.get_or_add_rPr(), CODE_FONT, CODE_SIZE, CODE_COLOR)
    if span.url is not None:
        run.font.color.rgb = RGBColor.from_string(LINK_COLOR)
        run.font.underline = WD_UNDERLINE.NONE if in_heading else WD_UNDERLINE.SINGLE


def _add_hyperlink(paragraph: DocxParagraph, span: Span, in_heading: bool) -> None:
    rid = paragraph.part.relate_to(span.url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rid)
    run = paragraph.add_run(f"`{span.text}`" if span.code else span.text)
    _format_run(run, span, in_heading)
    link.append(run.element)
    paragraph._p.append(link)


def add_spans(paragraph: DocxParagraph, spans: Sequence[Span], in_heading: bool = False) -> None:
    """Append spans as runs; code spans get visible backticks, links become hyperlinks."""
    for span in spans:
        if span.url is not None:
            _add_hyperlink(paragraph, span, in_heading)
            continue
        text = f"`{span.text}`" if span.code else span.text
        _format_run(paragraph.add_run(text), span, in_heading)


def _add_rule(document: DocxDocument) -> None:
    ppr = document.add_paragraph()._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("val", "single"), ("sz", str(RULE_SIZE)), ("space", "0"), ("color", RULE_COLOR)):
        bottom.set(qn(f"w:{key}"), value)
    borders.append(bottom)
    ppr.append(borders)


def _shade(paragraph: DocxParagraph, fill: str) -> None:
    shd = OxmlElement("w:shd")
    for key, value in (("val", "clear"), ("color", "auto"), ("fill", fill)):
        shd.set(qn(f"w:{key}"), value)
    paragraph._p.get_or_add_pPr().append(shd)


def _add_code_block(document: DocxDocument, block: CodeBlock) -> None:
    paragraph = document.add_paragraph()
    _shade(paragraph, BLOCK_FILL)  # first: w:shd must precede w:spacing and w:ind in w:pPr
    paragraph.paragraph_format.left_indent = Inches(0.25)
    paragraph.paragraph_format.line_spacing = 1.0
    for i, line in enumerate(block.text.split("\n")):
        run = paragraph.add_run()
        _apply_font(run.font, run.element.get_or_add_rPr(), CODE_FONT, CODE_SIZE, BLOCK_COLOR)
        if i:
            run.add_break()
        run.add_text(line)


def _new_num(document: DocxDocument, paragraph: DocxParagraph) -> int:
    """Add a w:num restarting at 1 on the abstract numbering of the paragraph's list style."""
    style_num = paragraph.style.element.pPr.numPr.numId.val
    numbering = document.part.numbering_part.element
    abstract_id = numbering.num_having_numId(style_num).abstractNumId.val
    num = numbering.add_num(abstract_id)
    num.add_lvlOverride(0).add_startOverride(1)
    return num.numId


def _starts_list(prev: Optional[Block], item: ListItem) -> bool:
    if not isinstance(prev, ListItem) or prev.level < item.level:
        return True
    return prev.level == item.level and prev.ordered != item.ordered


# ---------------------------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------------------------


@dataclass
class _RenderState:
    """Rendering context: link definitions, previous block, and the w:num of each open numbered level."""

    links: Dict[str, str]
    prev: Optional[Block] = None
    nums: Dict[int, int] = field(default_factory=dict)


def _number(document: DocxDocument, paragraph: DocxParagraph, item: ListItem, state: _RenderState) -> None:
    """Point a numbered item at its list's w:num; the first item of a list gets a fresh one."""
    if _starts_list(state.prev, item) or item.level not in state.nums:
        state.nums[item.level] = _new_num(document, paragraph)
    paragraph._p.get_or_add_pPr().get_or_add_numPr().get_or_add_numId().val = state.nums[item.level]


def _close_levels(item: ListItem, state: _RenderState) -> None:
    """Forget numbered lists the item closes: deeper levels, and its own level when it is a bullet."""
    closed = [lvl for lvl in state.nums if lvl > item.level or (lvl == item.level and not item.ordered)]
    for level in closed:
        del state.nums[level]


def _render_item(document: DocxDocument, item: ListItem, state: _RenderState) -> None:
    _close_levels(item, state)
    styles = NUMBER_STYLES if item.ordered else BULLET_STYLES
    paragraph = document.add_paragraph(style=styles[item.level])
    add_spans(paragraph, parse_inline(item.text, state.links))
    if item.ordered:
        _number(document, paragraph, item, state)


def _render_block(document: DocxDocument, block: Block, state: _RenderState) -> None:
    if isinstance(block, Heading):
        paragraph = document.add_paragraph(style=f"Heading {block.level}")
        add_spans(paragraph, parse_inline(block.text, state.links, detect=False), in_heading=True)
    elif isinstance(block, Paragraph):
        add_spans(document.add_paragraph(), parse_inline(block.text, state.links))
    elif isinstance(block, ListItem):
        _render_item(document, block, state)
    elif isinstance(block, CodeBlock):
        _add_code_block(document, block)
    else:
        _add_rule(document)
    if not isinstance(block, ListItem):
        state.nums.clear()
    state.prev = block


def _retitle(blocks: List[Block], title: Optional[str]) -> str:
    """Replace the first level-1 heading's text when a title is given; return the final title."""
    first = next((b for b in blocks if isinstance(b, Heading) and b.level == 1), None)
    if first is None:
        return title or ""
    if title:
        first.text = title
    return first.text


def convert_markdown(text: str, title: Optional[str] = None) -> DocxDocument:
    """Build a styled Word document from changelog Markdown text."""
    parsed = parse_markdown(text)
    blocks = filter_blocks(parsed.blocks)
    document = _setup_document(_retitle(blocks, title))
    state = _RenderState(parsed.links)
    for block in blocks:
        _render_block(document, block, state)
    return document


def convert_file(src: Union[str, Path], dst: Union[str, Path], title: Optional[str] = None) -> Path:
    """Convert a Markdown file to .docx at dst; return the output path."""
    out = Path(dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    convert_markdown(Path(src).read_text(encoding="utf-8-sig"), title).save(str(out))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point: convert one Markdown changelog to .docx."""
    parser = argparse.ArgumentParser(description="Convert a CHANGELOG.md to a styled .docx.")
    parser.add_argument("source", type=Path, help="Markdown file to read")
    parser.add_argument("output", type=Path, help=".docx file to write")
    parser.add_argument("--title", default=None, help="replacement text for the first # heading")
    args = parser.parse_args(argv)
    out = convert_file(args.source, args.output, args.title)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
