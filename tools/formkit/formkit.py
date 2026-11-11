#!/usr/bin/env python3
"""formkit — 帳票定義 → 書き込み可能 PDF の再生成と、原本との一致の実測。

サブコマンド:
  extract   PDF の1ページから罫線・文字の座標を取り出す（帳票定義の土台）
  generate  帳票定義＋データから、標準フォームフィールド付き PDF を作る
  measure   原本 PDF と再生成 PDF を比べ、罫線・文字・欄の誤差を数値で出す
  selftest  異常を仕込んだ試験（測定器が誤差・欠落・干渉を検出できるか）

座標系: 帳票定義はすべて PDF のユーザー空間（pt、原点は左下）で持つ。
原則: 座標が確定していない欄（coord_status != "確定"）はフィールドにしない。
      入りきらない値は黙って縮小しない（警告として記録し、フィールドの値は入れない）。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass, asdict

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,
    StreamObject, TextStringObject, BooleanObject,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

INPUT_TYPES = ("記号", "数値", "文字", "日付", "選択式", "固定・自動")
THIN_RECT = 1.5      # これより細い塗り矩形は「線」とみなす（Print To PDF は線を細い矩形で描く）
MERGE_TOL = 0.05     # 同一直線とみなす座標差（pt）
MERGE_GAP = 0.6      # つながっているとみなす隙間（pt）
SEARCH_R = 5.0       # 対応する線を探す半径（pt）
CHAR_R = 6.0         # 対応する文字を探す半径（pt）
MM = 25.4 / 72

DEFAULT_TTF = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
FIELD_FONT = "HeiseiKakuGo-W5"   # フォーム欄の表示用（非埋め込み CID フォント。最終フォントは未決 J7）


# ---------------------------------------------------------------- extract
@dataclass
class Seg:
    o: str          # "h" or "v"
    c: float        # h: y,  v: x   （PDF 座標、原点左下）
    a: float        # 区間の始点（h: x0, v: y0）
    b: float        # 区間の終点
    w: float        # 線の太さ

    @property
    def length(self):
        return self.b - self.a


def _segments_from_page(page) -> tuple[list[Seg], dict]:
    H = float(page.height)
    raw: list[Seg] = []
    stats = {"lines": 0, "rects_thin": 0, "rects_box": 0, "curves_ignored": len(page.curves)}
    for ln in page.lines:
        stats["lines"] += 1
        x0, x1 = sorted((float(ln["x0"]), float(ln["x1"])))
        y0, y1 = sorted((H - float(ln["top"]), H - float(ln["bottom"])))
        w = float(ln.get("linewidth") or 0)
        if abs(y1 - y0) <= abs(x1 - x0):
            raw.append(Seg("h", (y0 + y1) / 2, x0, x1, w))
        else:
            raw.append(Seg("v", (x0 + x1) / 2, y0, y1, w))
    for r in page.rects:
        x0, x1 = float(r["x0"]), float(r["x1"])
        y0, y1 = H - float(r["bottom"]), H - float(r["top"])
        wdt, hgt = x1 - x0, y1 - y0
        if hgt < THIN_RECT and wdt >= hgt:
            stats["rects_thin"] += 1
            raw.append(Seg("h", (y0 + y1) / 2, x0, x1, hgt))
        elif wdt < THIN_RECT:
            stats["rects_thin"] += 1
            raw.append(Seg("v", (x0 + x1) / 2, y0, y1, wdt))
        else:
            stats["rects_box"] += 1
            w = float(r.get("linewidth") or 0)
            raw += [Seg("h", y0, x0, x1, w), Seg("h", y1, x0, x1, w),
                    Seg("v", x0, y0, y1, w), Seg("v", x1, y0, y1, w)]
    return merge_segments(raw), stats


def merge_segments(segs: list[Seg]) -> list[Seg]:
    out: list[Seg] = []
    for o in ("h", "v"):
        group = sorted((s for s in segs if s.o == o), key=lambda s: (round(s.c, 1), s.a))
        cur: Seg | None = None
        for s in group:
            if cur and abs(s.c - cur.c) <= MERGE_TOL and s.a <= cur.b + MERGE_GAP:
                cur.b = max(cur.b, s.b)
                cur.w = max(cur.w, s.w)
            else:
                if cur:
                    out.append(cur)
                cur = Seg(o, s.c, s.a, s.b, s.w)
        if cur:
            out.append(cur)
    return [s for s in out if s.length > 0.5]


def _chars_from_page(page) -> list[dict]:
    chars = []
    for ch in page.chars:
        if not ch["text"].strip():
            continue
        m = ch.get("matrix") or (0, 0, 0, 0, ch["x0"], float(page.height) - ch["bottom"])
        chars.append({"t": ch["text"], "x": round(float(m[4]), 3), "y": round(float(m[5]), 3),
                      "size": round(float(ch["size"]), 3), "font": ch.get("fontname", "")})
    return chars


def extract(pdf_path: str, page_no: int = 1) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no - 1]
        segs, stats = _segments_from_page(page)
        return {
            "source": os.path.basename(pdf_path), "page": page_no,
            "page_size": [round(float(page.width), 3), round(float(page.height), 3)],
            "stats": stats,
            "lines": [[s.o, round(s.c, 3), round(s.a, 3), round(s.b, 3), round(s.w, 3)] for s in segs],
            "chars": _chars_from_page(page),
        }


def filter_chars_outside_fields(chars: list[dict], fields: list[dict]) -> tuple[list[dict], int]:
    """欄の枠の中にある文字は「記入」とみなして除く（顧客情報を定義に持ち込まない）。"""
    rects = [f["rect"] for f in fields if f.get("rect")]
    kept, dropped = [], 0
    for ch in chars:
        if any(r[0] - 0.5 <= ch["x"] <= r[2] + 0.5 and r[1] - 0.5 <= ch["y"] <= r[3] + 0.5 for r in rects):
            dropped += 1
        else:
            kept.append(ch)
    return kept, dropped


# ---------------------------------------------------------------- generate
_ttf_registered: dict[str, str] = {}


def _font(path: str) -> str:
    if path not in _ttf_registered:
        name = "F" + str(len(_ttf_registered))
        pdfmetrics.registerFont(TTFont(name, path))
        _ttf_registered[path] = name
    return _ttf_registered[path]


def check_value(field: dict, value: str, ef=None) -> list[str]:
    """値が欄の容量・許容値に収まるか。収まらない場合は理由を返す（黙って縮小しない）。"""
    issues = []
    if value in (None, ""):
        return issues
    t = field["input_type"]
    allowed = field.get("allowed")
    if t in ("記号", "選択式") and allowed and value not in allowed:
        issues.append(f"許容値外: {value!r} not in {allowed}")
    cap = field.get("capacity") or {}
    lines = str(value).split("\n")
    if cap.get("max_lines") and len(lines) > cap["max_lines"]:
        issues.append(f"行数超過: {len(lines)} > {cap['max_lines']}")
    if cap.get("max_chars_per_line"):
        over = [len(l) for l in lines if len(l) > cap["max_chars_per_line"]]
        if over:
            issues.append(f"1行の文字数超過: {max(over)} > {cap['max_chars_per_line']}")
    # 実寸でも確かめる（欄幅 − 余白 にフォントサイズで収まるか）
    if field.get("rect") and t != "記号":
        size = field.get("font_size", 9)
        avail = field["rect"][2] - field["rect"][0] - 2 * field.get("padding", 1.5)
        widest = max((ef.width(l, size) if ef else pdfmetrics.stringWidth(l, FIELD_FONT, size)) for l in lines)
        if ef and any(c in ef.missing for c in value):
            issues.append(f"フォントに無い字: {[c for c in value if c in ef.missing]}")
        need_h = size * 1.25 * (len(lines) - 1) + size
        if need_h > field["rect"][3] - field["rect"][1] + 0.01:
            issues.append(f"欄の高さ超過: {need_h:.1f}pt > {field['rect'][3] - field['rect'][1]:.1f}pt")
        if widest > avail + 0.01:
            issues.append(f"欄幅超過: {widest:.1f}pt > {avail:.1f}pt (size {size})")
    return issues


def _draw_static(defn: dict, out_path: str, ttf: str, flat_values: dict | None = None):
    """罫線と固定文字を描く。flat_values を渡すと記入値を文字として焼き込む（試験用の擬似原本）。"""
    W, H = defn["page_size"]
    c = canvas.Canvas(out_path, pagesize=(W, H))
    fname = _font(ttf)
    style = defn.get("line_style", "stroke")
    for o, cc, a, b, w in defn["lines"]:
        if style == "thin_rect":  # Print To PDF 風: 線を細い塗り矩形で描く
            w = max(w, 0.1)
            if o == "h":
                c.rect(a, cc - w / 2, b - a, w, stroke=0, fill=1)
            else:
                c.rect(cc - w / 2, a, w, b - a, stroke=0, fill=1)
        else:
            c.setLineWidth(w or 0.5)
            c.setLineCap(2)  # 角まで描く（端点の欠けを防ぐ）
            if o == "h":
                c.line(a - (w or 0.5) / 2 * 0, cc, b, cc)
            else:
                c.line(cc, a, cc, b)
    for ch in defn.get("chars", []):
        c.setFont(fname, ch["size"])
        c.drawString(ch["x"], ch["y"], ch["t"])
    if flat_values:
        for f in defn["fields"]:
            v = flat_values.get(f["id"])
            if v and f.get("rect"):
                size = f.get("font_size", 9)
                c.setFont(fname, size)
                c.drawString(f["rect"][0] + f.get("padding", 1.5), f["rect"][1] + (f["rect"][3] - f["rect"][1] - size) / 2 + 1, str(v))
    c.showPage()
    c.save()


class EmbeddedFont:
    """欄の外観ストリーム用の埋め込みフォント（使う字だけの部分埋め込み、Identity-H）。

    外観（/AP）はこのフォントで描くので、閲覧ソフトにフォントが無くても値が表示される。
    利用者が後から欄を編集するときは /DA の標準 CID フォント名（非埋め込み）が使われる。
    """

    def __init__(self, writer: PdfWriter, ttf_path: str, text: str):
        from fontTools.ttLib import TTFont as FTFont
        from fontTools import subset
        import io
        self.font = FTFont(ttf_path)
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        chars = sorted(set(text) | {" "})
        missing = [c for c in chars if ord(c) not in self.cmap]
        self.missing = missing
        opts = subset.Options(); opts.retain_gids = True; opts.notdef_outline = True
        opts.name_IDs = ["*"]; opts.drop_tables += ["GSUB", "GPOS", "GDEF"]
        sub = subset.Subsetter(opts); sub.populate(unicodes=[ord(c) for c in chars if ord(c) in self.cmap])
        f2 = FTFont(ttf_path); sub.subset(f2); buf = io.BytesIO(); f2.save(buf)
        hmtx = self.font["hmtx"]
        self.gid = {c: self.font.getGlyphID(self.cmap[ord(c)]) for c in chars if ord(c) in self.cmap}
        self.adv = {c: hmtx[self.cmap[ord(c)]][0] * 1000 / self.upm for c in self.gid}
        ff = StreamObject(); ff.set_data(buf.getvalue()); ff[NameObject("/Length1")] = NumberObject(len(buf.getvalue()))
        head, hhea = self.font["head"], self.font["hhea"]
        sc = lambda v: NumberObject(int(round(v * 1000 / self.upm)))
        base = "/YEGOAA+" + self.font["name"].getDebugName(6)
        desc = DictionaryObject({
            NameObject("/Type"): NameObject("/FontDescriptor"), NameObject("/FontName"): NameObject(base),
            NameObject("/Flags"): NumberObject(4),
            NameObject("/FontBBox"): ArrayObject([sc(head.xMin), sc(head.yMin), sc(head.xMax), sc(head.yMax)]),
            NameObject("/ItalicAngle"): NumberObject(0), NameObject("/Ascent"): sc(hhea.ascent),
            NameObject("/Descent"): sc(hhea.descent), NameObject("/CapHeight"): sc(hhea.ascent),
            NameObject("/StemV"): NumberObject(80), NameObject("/FontFile2"): writer._add_object(ff),
        })
        w = ArrayObject()
        for c, g in sorted(self.gid.items(), key=lambda kv: kv[1]):
            w += [NumberObject(g), ArrayObject([NumberObject(int(round(self.adv[c])))])]
        cid = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/CIDFontType2"),
            NameObject("/BaseFont"): NameObject(base),
            NameObject("/CIDSystemInfo"): DictionaryObject({
                NameObject("/Registry"): TextStringObject("Adobe"), NameObject("/Ordering"): TextStringObject("Identity"),
                NameObject("/Supplement"): NumberObject(0)}),
            NameObject("/FontDescriptor"): writer._add_object(desc), NameObject("/CIDToGIDMap"): NameObject("/Identity"),
            NameObject("/DW"): NumberObject(1000), NameObject("/W"): w,
        })
        bf = "\n".join(f"<{g:04X}> <{c.encode('utf-16-be').hex().upper()}>" for c, g in self.gid.items())
        cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) "
                "/Ordering (UCS) /Supplement 0 >> def /CMapName /Adobe-Identity-UCS def /CMapType 2 def "
                "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
                f"{len(self.gid)} beginbfchar\n{bf}\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end")
        tu = StreamObject(); tu.set_data(cmap.encode("ascii"))
        self.ref = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/BaseFont"): NameObject(base), NameObject("/Encoding"): NameObject("/Identity-H"),
            NameObject("/DescendantFonts"): ArrayObject([writer._add_object(cid)]),
            NameObject("/ToUnicode"): writer._add_object(tu),
        }))

    def width(self, s: str, size: float) -> float:
        return sum(self.adv.get(c, 1000) for c in s) * size / 1000

    def hex(self, s: str) -> str:
        return "".join(f"{self.gid.get(c, 0):04X}" for c in s)


def _appearance(writer: PdfWriter, field: dict, value: str, ef: "EmbeddedFont") -> StreamObject:
    x0, y0, x1, y1 = field["rect"]
    w, h = x1 - x0, y1 - y0
    size = field.get("font_size", 9)
    pad = field.get("padding", 1.5)
    ops = ["/Tx BMC", "q"]
    lines = value.split("\n") if value else []
    lead = size * 1.25
    for i, line in enumerate(lines):
        tw = ef.width(line, size)
        align = field.get("align", "center" if field["input_type"] == "記号" else "left")
        tx = {"left": pad, "center": (w - tw) / 2, "right": w - pad - tw}[align]
        block = lead * (len(lines) - 1) + size
        ty = (h + block) / 2 - size - i * lead + size * 0.12
        ops += ["BT", f"/FE {size:g} Tf", "0 g", f"{tx:.3f} {ty:.3f} Td", f"<{ef.hex(line)}> Tj", "ET"]
    ops += ["Q", "EMC"]
    st = StreamObject()
    st.set_data("\n".join(ops).encode("latin-1"))
    st.update({
        NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)]),
        NameObject("/Resources"): DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/FE"): ef.ref})}),
    })
    return writer._add_object(st)


def _cid_font(writer: PdfWriter):
    """編集時用（/DA）の日本語 CID フォント。非埋め込み・UniJIS-UCS2-H。閲覧ソフトが代替フォントで描く。"""
    desc = DictionaryObject({
        NameObject("/Type"): NameObject("/FontDescriptor"), NameObject("/FontName"): NameObject("/" + FIELD_FONT),
        NameObject("/Flags"): NumberObject(4),
        NameObject("/FontBBox"): ArrayObject([NumberObject(v) for v in (-92, -250, 1010, 922)]),
        NameObject("/ItalicAngle"): NumberObject(0), NameObject("/Ascent"): NumberObject(752),
        NameObject("/Descent"): NumberObject(-221), NameObject("/CapHeight"): NumberObject(737),
        NameObject("/StemV"): NumberObject(114),
    })
    cid = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/CIDFontType0"),
        NameObject("/BaseFont"): NameObject("/" + FIELD_FONT),
        NameObject("/CIDSystemInfo"): DictionaryObject({
            NameObject("/Registry"): TextStringObject("Adobe"), NameObject("/Ordering"): TextStringObject("Japan1"),
            NameObject("/Supplement"): NumberObject(2)}),
        NameObject("/FontDescriptor"): writer._add_object(desc), NameObject("/DW"): NumberObject(1000),
    })
    return writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type0"),
        NameObject("/BaseFont"): NameObject("/" + FIELD_FONT), NameObject("/Encoding"): NameObject("/UniJIS-UCS2-H"),
        NameObject("/DescendantFonts"): ArrayObject([writer._add_object(cid)]),
    }))


def generate(defn: dict, data: dict, out_path: str, ttf: str = DEFAULT_TTF, log: list | None = None) -> dict:
    log = log if log is not None else []
    pdfmetrics.registerFont(UnicodeCIDFont(FIELD_FONT))
    tmp = out_path + ".static.pdf"
    _draw_static(defn, tmp, ttf)
    writer = PdfWriter(clone_from=PdfReader(tmp))
    os.remove(tmp)
    page = writer.pages[0]
    font_ref = _cid_font(writer)
    values = {}
    for f in defn["fields"]:
        v = data.get(f["id"], "")
        values[f["id"]] = "" if v is None else str(v)
    ef = EmbeddedFont(writer, ttf, "".join(values.values()))
    annots = ArrayObject()
    fields = ArrayObject()
    report = {"fields_created": 0, "fields_skipped": [], "value_issues": []}
    for f in defn["fields"]:
        if f.get("input_type") not in INPUT_TYPES:
            report["fields_skipped"].append({"id": f["id"], "reason": f"未知の入力形式 {f.get('input_type')!r}"})
            continue
        if f.get("coord_status") != "確定" or not f.get("rect"):
            report["fields_skipped"].append({"id": f["id"], "reason": "座標未確定のためフィールドを作らない（編集禁止）"})
            continue
        value = values[f["id"]]
        issues = check_value(f, value, ef)
        if issues:
            report["value_issues"].append({"id": f["id"], "value_len": len(value), "issues": issues})
            value = ""  # 入りきらない／許容外の値は入れない（黙って縮小しない）
        t = f["input_type"]
        flags = 0
        if t == "固定・自動":
            flags |= 1  # ReadOnly
        if (f.get("capacity") or {}).get("max_lines", 1) > 1:
            flags |= 1 << 12  # Multiline
        widget = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/T"): TextStringObject(f["id"]), NameObject("/TU"): TextStringObject(f.get("label", "")),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in f["rect"]]),
            NameObject("/F"): NumberObject(4), NameObject("/P"): page.indirect_reference,
            NameObject("/DA"): TextStringObject(f"/FJ {f.get('font_size', 9):g} Tf 0 g"),
            NameObject("/V"): TextStringObject(value),
            NameObject("/MK"): DictionaryObject(),
        })
        if t in ("記号", "選択式"):
            widget[NameObject("/FT")] = NameObject("/Ch")
            flags |= 1 << 17  # Combo
            widget[NameObject("/Opt")] = ArrayObject([TextStringObject(o) for o in [""] + list(f.get("allowed", []))])
        else:
            widget[NameObject("/FT")] = NameObject("/Tx")
            if (f.get("capacity") or {}).get("max_chars"):
                widget[NameObject("/MaxLen")] = NumberObject(f["capacity"]["max_chars"])
        widget[NameObject("/Ff")] = NumberObject(flags)
        widget[NameObject("/AP")] = DictionaryObject({NameObject("/N"): _appearance(writer, f, value, ef)})
        ref = writer._add_object(widget)
        annots.append(ref)
        fields.append(ref)
        report["fields_created"] += 1
    # 内部リンク（同一 PDF 内のページへ）。パッケージ組み立て時に使う
    for ln in defn.get("links", []):
        if ln.get("target_page") is None or ln["target_page"] >= len(writer.pages):
            report.setdefault("links_skipped", []).append(ln.get("id"))
            continue
        annots.append(writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in ln["rect"]]),
            NameObject("/Border"): ArrayObject([NumberObject(0)] * 3),
            NameObject("/Dest"): ArrayObject([writer.pages[ln["target_page"]].indirect_reference, NameObject("/Fit")]),
        })))
    page[NameObject("/Annots")] = annots
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(DictionaryObject({
        NameObject("/Fields"): fields,
        NameObject("/DR"): DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/FJ"): font_ref, NameObject("/FE"): ef.ref})}),
        NameObject("/DA"): TextStringObject("/FJ 9 Tf 0 g"),
        NameObject("/NeedAppearances"): BooleanObject(False),
    }))
    writer.add_metadata({"/Title": defn.get("title", ""), "/Subject": f"form={defn.get('form_id')} version={defn.get('version')} lineage={defn.get('lineage')}"})
    with open(out_path, "wb") as fh:
        writer.write(fh)
    report["appearance_font"] = {"embedded_subset": str(ef.ref.get_object()["/BaseFont"]), "missing_glyphs": ef.missing,
                                 "edit_font_DA": FIELD_FONT + "（非埋め込み）"}
    log.append(report)
    return report


# ---------------------------------------------------------------- measure
def _match_segments(orig: list[Seg], gen: list[Seg]):
    rows, used = [], set()
    for i, s in enumerate(orig):
        best, bj = None, None
        for j, g in enumerate(gen):
            if g.o != s.o or abs(g.c - s.c) > SEARCH_R:
                continue
            ov = min(s.b, g.b) - max(s.a, g.a)
            if ov < 0.5 * min(s.length, g.length):
                continue
            score = abs(g.c - s.c) + 0.1 * (abs(g.a - s.a) + abs(g.b - s.b))
            if best is None or score < best:
                best, bj = score, j
        if bj is None:
            rows.append({"kind": "line", "id": f"{s.o}{i}", "o": s.o, "c": round(s.c, 3), "a": round(s.a, 3), "b": round(s.b, 3),
                         "status": "原本にあり再生成に無い"})
            continue
        g = gen[bj]
        used.add(bj)
        rows.append({"kind": "line", "id": f"{s.o}{i}", "o": s.o, "c": round(s.c, 3), "a": round(s.a, 3), "b": round(s.b, 3),
                     "status": "対応あり", "d_pos": round(g.c - s.c, 4), "d_start": round(g.a - s.a, 4),
                     "d_end": round(g.b - s.b, 4), "d_width": round(g.w - s.w, 4)})
    for j, g in enumerate(gen):
        if j not in used:
            rows.append({"kind": "line", "id": f"gen-{g.o}{j}", "o": g.o, "c": round(g.c, 3), "a": round(g.a, 3), "b": round(g.b, 3),
                         "status": "再生成にあり原本に無い"})
    return rows


def _match_chars(orig: list[dict], gen: list[dict]):
    rows, used = [], set()
    for i, ch in enumerate(orig):
        best, bj = None, None
        for j, g in enumerate(gen):
            if j in used or g["t"] != ch["t"]:
                continue
            d = math.hypot(g["x"] - ch["x"], g["y"] - ch["y"])
            if d <= CHAR_R and (best is None or d < best):
                best, bj = d, j
        if bj is None:
            rows.append({"kind": "char", "id": f"c{i}", "text": ch["t"], "x": ch["x"], "y": ch["y"], "status": "原本にあり再生成に無い"})
            continue
        used.add(bj)
        g = gen[bj]
        rows.append({"kind": "char", "id": f"c{i}", "text": ch["t"], "x": ch["x"], "y": ch["y"], "status": "対応あり",
                     "d_x": round(g["x"] - ch["x"], 4), "d_y": round(g["y"] - ch["y"], 4), "d_size": round(g["size"] - ch["size"], 4)})
    for j, g in enumerate(gen):
        if j not in used:
            rows.append({"kind": "char", "id": f"gen-c{j}", "text": g["t"], "x": g["x"], "y": g["y"], "status": "再生成にあり原本に無い"})
    return rows


def _field_rows(gen_pdf: str, orig_segs: list[Seg], defn: dict | None):
    rows = []
    reader = PdfReader(gen_pdf)
    page = reader.pages[0]
    want = {f["id"]: f for f in (defn or {}).get("fields", [])}
    for a in page.get("/Annots", []) or []:
        a = a.get_object()
        if a.get("/Subtype") != "/Widget":
            continue
        fid = str(a.get("/T"))
        x0, y0, x1, y1 = [float(v) for v in a["/Rect"]]
        inner = (x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3)
        hits = []
        for s in orig_segs:
            if s.o == "h" and inner[1] < s.c < inner[3] and min(s.b, inner[2]) - max(s.a, inner[0]) > 0:
                hits.append(f"h@{s.c:.2f}")
            if s.o == "v" and inner[0] < s.c < inner[2] and min(s.b, inner[3]) - max(s.a, inner[1]) > 0:
                hits.append(f"v@{s.c:.2f}")
        row = {"kind": "field", "id": fid, "x": round(x0, 3), "y": round(y0, 3), "status": "罫線干渉" if hits else "枠内",
               "crossing": " ".join(hits)}
        if fid in want and want[fid].get("rect"):
            r = want[fid]["rect"]
            row["d_rect_max"] = round(max(abs(p - q) for p, q in zip((x0, y0, x1, y1), r)), 4)
        rows.append(row)
    return rows


def _summ(vals):
    vals = [abs(v) for v in vals]
    if not vals:
        return {"n": 0}
    vals.sort()
    p95 = vals[min(len(vals) - 1, int(math.ceil(0.95 * len(vals))) - 1)]
    return {"n": len(vals), "max_pt": round(vals[-1], 4), "p95_pt": round(p95, 4), "mean_pt": round(statistics.fmean(vals), 4),
            "max_mm": round(vals[-1] * MM, 4)}


def measure(orig_pdf: str, gen_pdf: str, defn: dict | None = None, orig_page: int = 1, csv_path: str | None = None) -> dict:
    o, g = extract(orig_pdf, orig_page), extract(gen_pdf, 1)
    oseg = [Seg(*l) for l in o["lines"]]
    gseg = [Seg(*l) for l in g["lines"]]
    ochars = o["chars"]
    dropped = 0
    if defn:  # 原本側の記入文字（欄の中）は比較から除く
        ochars, dropped = filter_chars_outside_fields(ochars, defn["fields"])
    line_rows = _match_segments(oseg, gseg)
    char_rows = _match_chars(ochars, g["chars"])
    field_rows = _field_rows(gen_pdf, oseg, defn)
    ok_l = [r for r in line_rows if r["status"] == "対応あり"]
    ok_c = [r for r in char_rows if r["status"] == "対応あり"]
    summary = {
        "page_size": {"orig": o["page_size"], "gen": g["page_size"],
                      "d_max_pt": round(max(abs(a - b) for a, b in zip(o["page_size"], g["page_size"])), 4)},
        "lines": {"orig": len(oseg), "gen": len(gseg), "matched": len(ok_l),
                  "missing_in_gen": sum(r["status"] == "原本にあり再生成に無い" for r in line_rows),
                  "extra_in_gen": sum(r["status"] == "再生成にあり原本に無い" for r in line_rows),
                  "pos": _summ([r["d_pos"] for r in ok_l]),
                  "ends": _summ([r["d_start"] for r in ok_l] + [r["d_end"] for r in ok_l]),
                  "width": _summ([r["d_width"] for r in ok_l])},
        "chars": {"orig_fixed": len(ochars), "orig_in_fields_excluded": dropped, "gen": len(g["chars"]), "matched": len(ok_c),
                  "missing_in_gen": sum(r["status"] == "原本にあり再生成に無い" for r in char_rows),
                  "extra_in_gen": sum(r["status"] == "再生成にあり原本に無い" for r in char_rows),
                  "x": _summ([r["d_x"] for r in ok_c]), "y": _summ([r["d_y"] for r in ok_c]),
                  "size": _summ([r["d_size"] for r in ok_c])},
        "fields": {"n": len(field_rows), "interfering": sum(r["status"] == "罫線干渉" for r in field_rows),
                   "rect_vs_definition": _summ([r["d_rect_max"] for r in field_rows if "d_rect_max" in r])},
        "extract_stats": {"orig": o["stats"], "gen": g["stats"]},
    }
    if csv_path:
        keys = ["kind", "id", "status", "o", "c", "a", "b", "text", "x", "y", "d_pos", "d_start", "d_end", "d_width",
                "d_x", "d_y", "d_size", "d_rect_max", "crossing"]
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in line_rows + char_rows + field_rows:
                w.writerow(r)
    return summary


# ---------------------------------------------------------------- definition helpers
def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_definition(defn: dict) -> list[str]:
    errs = []
    for k in ("form_id", "version", "lineage", "page_size", "lines", "fields"):
        if k not in defn:
            errs.append(f"必須キーが無い: {k}")
    ids = set()
    for f in defn.get("fields", []):
        if f["id"] in ids:
            errs.append(f"欄 ID の重複: {f['id']}")
        ids.add(f["id"])
        if f.get("input_type") not in INPUT_TYPES:
            errs.append(f"{f['id']}: 入力形式が6種に無い {f.get('input_type')!r}")
        if f.get("coord_status") == "確定" and not f.get("rect"):
            errs.append(f"{f['id']}: 確定なのに rect が無い")
        if f.get("input_type") in ("記号", "選択式") and not f.get("allowed"):
            errs.append(f"{f['id']}: 許容値 allowed が無い")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("pdf"); e.add_argument("--page", type=int, default=1)
    e.add_argument("--fields-from", help="帳票定義。欄の中の文字（記入）を除いて出力する"); e.add_argument("-o")
    g = sub.add_parser("generate"); g.add_argument("definition"); g.add_argument("data"); g.add_argument("-o", required=True)
    m = sub.add_parser("measure"); m.add_argument("orig"); m.add_argument("gen"); m.add_argument("--definition")
    m.add_argument("--page", type=int, default=1); m.add_argument("--csv"); m.add_argument("-o")
    v = sub.add_parser("validate"); v.add_argument("definition")
    sub.add_parser("selftest").add_argument("--outdir", default="results/formkit-selftest")
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        res = extract(a.pdf, a.page)
        if a.fields_from:
            res["chars"], res["chars_in_fields_dropped"] = filter_chars_outside_fields(res["chars"], load(a.fields_from)["fields"])
        txt = json.dumps(res, ensure_ascii=False, indent=1)
        open(a.o, "w", encoding="utf-8").write(txt) if a.o else print(txt)
    elif a.cmd == "generate":
        print(json.dumps(generate(load(a.definition), load(a.data), a.o), ensure_ascii=False, indent=1))
    elif a.cmd == "measure":
        s = measure(a.orig, a.gen, load(a.definition) if a.definition else None, a.page, a.csv)
        txt = json.dumps(s, ensure_ascii=False, indent=1)
        open(a.o, "w", encoding="utf-8").write(txt) if a.o else print(txt)
    elif a.cmd == "validate":
        errs = validate_definition(load(a.definition))
        print("\n".join(errs) or "OK")
        sys.exit(1 if errs else 0)
    elif a.cmd == "selftest":
        from selftest import run
        sys.exit(run(a.outdir))


if __name__ == "__main__":
    main()
