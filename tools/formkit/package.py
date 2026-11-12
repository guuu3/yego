"""パッケージ組み立て：複数の型（シート）を1冊の PDF にまとめる。

- 各シートは formkit.generate で作る（欄名はシートの key を接頭辞にして重なりを避ける）
- 台帳系の型（同じ series のシートが続くもの）は、各シート右上に（i/n）の枚数表示を付ける。
  n は物件の総数から決まる（事業側 2026-11-11）。表示位置は型の定義 `sheet_counter` に持ち、
  座標が確定していなければ描かずに記録する
- 様式第1 の設備行から、その設備の点検様式の先頭ページへ PDF 内部リンクを付ける（事業側 2026-11-11）。
  リンク先が見つからない・リンク元の欄が無い場合は、リンクを作らずに「未解決」として記録する

パッケージ仕様（JSON）:
{
  "package_id": "...",
  "sheets": [{"key": "cover", "definition": "<path>", "data": "<path>" | {...},
              "equipment": "消火器具" | null, "series": "ext-ledger" | null}, ...],
  "links":  [{"from": "cover", "field": "equip_1", "to_equipment": "消火器具"}, ...]
}
パスは仕様ファイルのあるフォルダからの相対。
"""
from __future__ import annotations

import copy
import json
import os
import tempfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject
from reportlab.pdfbase import pdfmetrics

import formkit as fk


class PackageError(ValueError):
    pass


def _load_ref(v, base):
    if isinstance(v, dict):
        return v
    return fk.load(os.path.join(base, v))


def plan(spec: dict) -> dict:
    """シートの順番・ページ番号・枚数表示・リンク先を決める（PDF はまだ作らない）。"""
    keys = [s["key"] for s in spec["sheets"]]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise PackageError(f"シートの key が重複している: {dup}")
    series_total: dict[str, int] = {}
    for s in spec["sheets"]:
        if s.get("series"):
            series_total[s["series"]] = series_total.get(s["series"], 0) + 1
    seen: dict[str, int] = {}
    pages = []
    for i, s in enumerate(spec["sheets"]):
        counter = None
        if s.get("series"):
            seen[s["series"]] = seen.get(s["series"], 0) + 1
            counter = (seen[s["series"]], series_total[s["series"]])
        pages.append({"key": s["key"], "page": i, "equipment": s.get("equipment"), "series": s.get("series"), "counter": counter})
    first_page = {}
    for pg in pages:
        if pg["equipment"] and pg["equipment"] not in first_page:
            first_page[pg["equipment"]] = pg["page"]
    return {"pages": pages, "equipment_first_page": first_page}


def assemble(spec: dict, out_path: str, base_dir: str = ".", ttf: str = fk.DEFAULT_TTF) -> dict:
    pl = plan(spec)
    report = {"package_id": spec.get("package_id"), "pages": len(pl["pages"]), "sheets": [], "counters": [], "links": []}
    tmpdir = tempfile.mkdtemp(prefix="yego-pkg-")
    parts = []
    for s, pg in zip(spec["sheets"], pl["pages"]):
        defn = copy.deepcopy(_load_ref(s["definition"], base_dir))
        data = _load_ref(s.get("data") or {}, base_dir)
        if pg["counter"]:
            i, n = pg["counter"]
            sc = defn.get("sheet_counter")
            text = (sc or {}).get("format", "（{i}/{n}）").format(i=i, n=n)
            if sc and sc.get("coord_status") == "確定":
                size = sc.get("size", 9)
                x = sc["x_right"] - pdfmetrics.stringWidth(text, fk._font(ttf), size)
                defn.setdefault("chars", []).append({"t": text, "x": round(x, 3), "y": sc["y"], "size": size})
                report["counters"].append({"key": s["key"], "text": text, "status": "描画"})
            else:
                report["counters"].append({"key": s["key"], "text": text, "status": "未描画（枚数表示の座標が未確定）"})
        part = os.path.join(tmpdir, f"{pg['page']:03d}.pdf")
        rep = fk.generate(defn, data, part, ttf=ttf, field_prefix=f"{s['key']}.")
        report["sheets"].append({"key": s["key"], "page": pg["page"] + 1, "form_id": defn.get("form_id"),
                                 "version": defn.get("version"), "fields_created": rep["fields_created"],
                                 "fields_skipped": len(rep["fields_skipped"]), "value_issues": rep["value_issues"]})
        parts.append(part)

    writer = PdfWriter()
    for part in parts:
        writer.add_page(PdfReader(part).pages[0])
    all_fields = ArrayObject()
    widgets = {}
    for pno, page in enumerate(writer.pages):
        for a in page.get("/Annots", []) or []:
            obj = a.get_object()
            if obj.get("/Subtype") == "/Widget":
                obj[NameObject("/P")] = page.indirect_reference
                all_fields.append(a)
                widgets[str(obj["/T"])] = (pno, [float(v) for v in obj["/Rect"]], int(obj.get("/Ff", 0)) & 1 == 1)

    key_page = {pg["key"]: pg["page"] for pg in pl["pages"]}
    for ln in spec.get("links", []):
        name = f"{ln['from']}.{ln['field']}"
        row = {"from": ln["from"], "field": ln["field"], "to_equipment": ln["to_equipment"]}
        target = pl["equipment_first_page"].get(ln["to_equipment"])
        if ln["from"] not in key_page:
            row["status"] = "未解決（リンク元のシートが無い）"
        elif name not in widgets:
            row["status"] = "未解決（リンク元の欄が無い。座標未確定の可能性）"
        elif target is None:
            row["status"] = "未解決（リンク先の設備がパッケージに無い）"
        else:
            pno, rect, readonly = widgets[name]
            page = writer.pages[pno]
            link = writer._add_object(DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
                NameObject("/Border"): ArrayObject([NumberObject(0)] * 3),
                NameObject("/Dest"): ArrayObject([writer.pages[target].indirect_reference, NameObject("/Fit")]),
            }))
            # 注釈は後ろにあるものほど上に重なり、クリックを受ける。
            # 読み取り専用の欄（設備行＝固定・自動）ではリンクを上に置き、クリックで移動できるようにする。
            # 編集できる欄と重なる場合は欄を上にし（編集を妨げない）、リンクが効かない可能性を記録する
            if readonly:
                page[NameObject("/Annots")] = ArrayObject(list(page["/Annots"]) + [link])
                row.update(status="作成", from_page=pno + 1, to_page=target + 1)
            else:
                page[NameObject("/Annots")] = ArrayObject([link] + list(page["/Annots"]))
                row.update(status="作成（注意：編集できる欄と重なり、クリックでは移動しない可能性）",
                           from_page=pno + 1, to_page=target + 1)
        report["links"].append(row)

    font_ref = fk._cid_font(writer)
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(DictionaryObject({
        NameObject("/Fields"): all_fields,
        NameObject("/DR"): DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/FJ"): font_ref})}),
        NameObject("/DA"): TextStringObject("/FJ 9 Tf 0 g"),
        NameObject("/NeedAppearances"): BooleanObject(False),
    }))
    writer.add_metadata({"/Title": spec.get("package_id", ""),
                         "/Subject": "yEgo package: " + ", ".join(f"{x['key']}={x['form_id']} v{x['version']}" for x in report["sheets"])})
    with open(out_path, "wb") as fh:
        writer.write(fh)
    for part in parts:
        os.remove(part)
    os.rmdir(tmpdir)
    report["fields_total"] = len(all_fields)
    return report


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="パッケージ組み立て")
    ap.add_argument("spec"); ap.add_argument("-o", required=True)
    a = ap.parse_args(argv)
    spec = fk.load(a.spec)
    print(json.dumps(assemble(spec, a.o, os.path.dirname(os.path.abspath(a.spec))), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
