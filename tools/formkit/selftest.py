"""異常を仕込んだ試験（formkit の測定器・生成器が、ずれ・欠落・干渉・はみ出しを検出できるか）。

原本 PDF は使わない。架空のダミー様式（TEST-A4、規定様式ではない）と匿名のダミーデータだけで回す。
試験の合否は「測定器が仕込んだ異常を検出したか」であり、帳票の一致の合否ではない。
"""
from __future__ import annotations

import copy
import csv
import json
import os

from pypdf import PdfReader

import formkit as fk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DUMMY_DEF = os.path.join(REPO, "forms", "definitions", "test", "TEST-A4.v0.1.json")
DUMMY_DATA = os.path.join(REPO, "forms", "data", "test", "TEST-A4.dummy.json")


def _run_case(name, expect, observed, ok, rows):
    rows.append({"case": name, "expect": expect, "observed": observed, "result": "PASS" if ok else "FAIL"})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {observed}")


def field_ink(pdf_path: str, defn: dict, dpi: int = 100, page: int = 1) -> dict:
    """pdftoppm で灰色画像にし、各欄の内側の黒い画素の割合を返す（罫線を避けて内側 2pt だけ見る）。"""
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(page), "-l", str(page), pdf_path, os.path.join(td, "p")],
                       check=True, capture_output=True)
        fn = [n for n in os.listdir(td) if n.endswith(".pgm")][0]
        raw = open(os.path.join(td, fn), "rb").read()
    parts = raw.split(maxsplit=4)
    W, H = int(parts[1]), int(parts[2]); px = parts[4]
    sc = dpi / 72; PH = defn["page_size"][1]
    out = {}
    for f in defn["fields"]:
        if not f.get("rect"):
            continue
        x0, y0, x1, y1 = f["rect"]
        cx0, cx1 = int((x0 + 2) * sc), int((x1 - 2) * sc)
        cy0, cy1 = int((PH - y1 + 2) * sc), int((PH - y0 - 2) * sc)
        tot = dark = 0
        for yy in range(cy0, cy1):
            row = px[yy * W + cx0: yy * W + cx1]
            tot += len(row); dark += sum(1 for b in row if b < 128)
        out[f["id"]] = dark / tot if tot else 0.0
    return out


def roundtrip_definition(defn: dict, orig_pdf: str) -> dict:
    """擬似原本から罫線・固定文字を抽出し、欄の定義と合わせて帳票定義を作る（実帳票で行う手順と同じ）。"""
    ex = fk.extract(orig_pdf)
    chars, dropped = fk.filter_chars_outside_fields(ex["chars"], defn["fields"])
    d = copy.deepcopy(defn)
    d["lines"] = ex["lines"]
    d["chars"] = chars
    d["line_style"] = "stroke"
    d["geometry_source"] = {"from": "extract", "page_size": ex["page_size"], "chars_in_fields_dropped": dropped}
    return d


PKG_SPEC = os.path.join(REPO, "forms", "packages", "test", "TEST-PKG.json")


def run_package(outdir: str, rows: list):
    """パッケージ組み立ての試験（枚数表示・内部リンク・欄名の重なり・未解決の記録）。"""
    import pdfplumber
    import package as pk
    p = lambda n: os.path.join(outdir, n)
    base = os.path.dirname(PKG_SPEC)
    spec = fk.load(PKG_SPEC)
    rep = pk.assemble(spec, p("package.pdf"), base)
    json.dump(rep, open(p("package-report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = PdfReader(p("package.pdf"))
    fields = r.get_fields() or {}
    _run_case("P1 ページ数と欄の数", "4ページ・102欄・欄名の重なり無し", f"pages {len(r.pages)} fields {len(fields)} total {rep['fields_total']}",
              len(r.pages) == 4 and len(fields) == rep["fields_total"] == 102, rows)
    v1, v2 = fields.get("ext2.r3_place", {}).get("/V"), fields.get("cover.judge_2", {}).get("/V")
    _run_case("P2 シートごとの値の読み戻し", "ext2.r3_place と cover.judge_2 が一致", f"{v1!r} {v2!r}",
              v1 == "2階 消火器 13（ダミー）" and v2 == "×", rows)
    links = []
    for a in r.pages[0].get("/Annots", []):
        o = a.get_object()
        if o.get("/Subtype") == "/Link":
            dest = o["/Dest"][0].get_object()
            links.append(next(i for i, pg in enumerate(r.pages) if pg.get_object() == dest) + 1)
    last = r.pages[0]["/Annots"][-1].get_object().get("/Subtype")
    _run_case("P3 様式第1相当の設備行から先頭ページへのリンク", "消火器具→2ページ、誘導灯→4ページ（2枚目の3ページではない）、リンクが最前面",
              f"links→{links} 最前面 {last}", sorted(links) == [2, 4] and last == "/Link", rows)
    with pdfplumber.open(p("package.pdf")) as pdf:
        texts = [pdf.pages[i].extract_text() or "" for i in range(4)]
    want = {1: "（1/2）", 2: "（2/2）", 3: "（1/1）"}
    got = {i: w in texts[i] for i, w in want.items()}
    _run_case("P4 台帳シートの枚数表示（i/n）", "2〜4ページに（1/2）（2/2）（1/1）、表紙には無い", f"{got} 表紙に有り {'/' in texts[0] and '（1/' in texts[0]}",
              all(got.values()) and "（1/" not in texts[0], rows)
    led = fk.load(os.path.join(base, spec["sheets"][2]["definition"]))
    ink = field_ink(p("package.pdf"), led, page=3)
    filled = [ink[f"r{i}_place"] > 0.002 for i in range(1, 11)]
    _run_case("P5 2枚目の台帳の表示（値のある行だけに描画）", "1〜3行目に描画、4〜10行目は空", f"{filled}", filled == [True] * 3 + [False] * 7, rows)
    fk.generate(led, spec["sheets"][2]["data"], p("p6-standalone.pdf"))
    m = fk.measure(p("package.pdf"), p("p6-standalone.pdf"), orig_page=3)
    _run_case("P6 組み立てで形が崩れない（3ページ目と単体生成を比較）", "罫線誤差0、差は枚数表示の5字だけ",
              f"lines matched {m['lines']['matched']}/{m['lines']['orig']} pos {m['lines']['pos'].get('max_pt')} chars missing {m['chars']['missing_in_gen']}",
              m["lines"]["matched"] == m["lines"]["orig"] == m["lines"]["gen"] and m["lines"]["pos"]["max_pt"] == 0 and m["chars"]["missing_in_gen"] == 5
              and m["chars"]["extra_in_gen"] == 0, rows)
    sp = copy.deepcopy(spec); sp["links"].append({"from": "cover", "field": "equip_1", "to_equipment": "自動火災報知設備"})
    rr = pk.assemble(sp, p("p7.pdf"), base)
    _run_case("P7 リンク先の設備がパッケージに無い", "リンクを作らず未解決として記録", f"{rr['links'][-1]['status']}",
              rr["links"][-1]["status"].startswith("未解決") and sum(x["status"].startswith("作成") for x in rr["links"]) == 2, rows)
    sp = copy.deepcopy(spec); sp["sheets"][2]["key"] = "ext1"
    try:
        pk.assemble(sp, p("p8.pdf"), base); ok, obs = False, "例外なし"
    except pk.PackageError as e:
        ok, obs = True, str(e)
    _run_case("P8 シートの key の重複", "組み立てを止める", obs, ok, rows)
    sp = copy.deepcopy(spec); d = copy.deepcopy(led); d["sheet_counter"]["coord_status"] = "未確定"
    for s in sp["sheets"][1:]:
        s["definition"] = d
    rr = pk.assemble(sp, p("p9.pdf"), base)
    with pdfplumber.open(p("p9.pdf")) as pdf:
        t = pdf.pages[1].extract_text() or ""
    _run_case("P9 枚数表示の座標が未確定", "描かずに記録", f"{[c['status'] for c in rr['counters']]} 描画あり {'（1/2）' in t}",
              all(c["status"].startswith("未描画") for c in rr["counters"]) and "（1/2）" not in t, rows)
    sp = copy.deepcopy(spec); cov = copy.deepcopy(fk.load(os.path.join(base, spec["sheets"][0]["definition"])))
    next(f for f in cov["fields"] if f["id"] == "equip_1")["coord_status"] = "未確定"
    sp["sheets"][0]["definition"] = cov
    rr = pk.assemble(sp, p("p10.pdf"), base)
    _run_case("P10 リンク元の欄が座標未確定", "リンクを作らず未解決として記録", f"{rr['links'][0]['status']}", rr["links"][0]["status"].startswith("未解決"), rows)
    sp = copy.deepcopy(spec); sp["links"] = [{"from": "cover", "field": "remarks", "to_equipment": "消火器具"}]
    rr = pk.assemble(sp, p("p11.pdf"), base)
    _run_case("P11 編集できる欄にリンク", "作成するが注意を記録（欄の編集を優先）", f"{rr['links'][0]['status']}", "注意" in rr["links"][0]["status"], rows)


def run(outdir: str) -> int:
    os.makedirs(outdir, exist_ok=True)
    defn = fk.load(DUMMY_DEF)
    data = fk.load(DUMMY_DATA)
    errs = fk.validate_definition(defn)
    assert not errs, errs
    p = lambda n: os.path.join(outdir, n)
    rows: list[dict] = []

    # 擬似原本: Print To PDF 風（線を細い塗り矩形）＋ 記入値を文字として焼き込み
    orig_def = dict(defn, line_style="thin_rect")
    fk._draw_static(orig_def, p("orig.pdf"), fk.DEFAULT_TTF, flat_values=data)

    # 基準: 抽出 → 定義 → 再生成 → 実測
    d2 = roundtrip_definition(defn, p("orig.pdf"))
    json.dump(d2, open(p("TEST-A4.extracted-definition.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rep = fk.generate(d2, data, p("gen.pdf"))
    base = fk.measure(p("orig.pdf"), p("gen.pdf"), d2, csv_path=p("baseline-measure.csv"))
    json.dump({"generate": rep, "measure": base}, open(p("baseline-summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L, C, F = base["lines"], base["chars"], base["fields"]
    _run_case("T0 基準(異常なし)・罫線", "対応率100%・位置誤差0", f"matched {L['matched']}/{L['orig']} missing {L['missing_in_gen']} extra {L['extra_in_gen']} pos {L['pos']}",
              L["matched"] == L["orig"] == L["gen"] and L["pos"].get("max_pt", 1) < 1e-3, rows)
    _run_case("T0 基準(異常なし)・固定文字", "対応率100%・位置誤差0、記入文字は除外", f"matched {C['matched']}/{C['orig_fixed']} excluded {C['orig_in_fields_excluded']} x {C['x'].get('max_pt')} y {C['y'].get('max_pt')}",
              C["matched"] == C["orig_fixed"] and C["missing_in_gen"] == 0 and C["x"].get("max_pt", 1) < 1e-3 and C["y"].get("max_pt", 1) < 1e-3 and C["orig_in_fields_excluded"] > 0, rows)
    _run_case("T0 基準(異常なし)・欄", "罫線干渉0", f"fields {F['n']} interfering {F['interfering']}", F["interfering"] == 0 and F["n"] == rep["fields_created"], rows)

    # 生成 PDF のフィールドを第三者ツール(pypdf)で読み、値と型を確かめる
    fields = PdfReader(p("gen.pdf")).get_fields()
    mismatch = [k for k, v in data.items() if k in fields and v and str(fields[k].get("/V")) != str(v)
                and not any(i["id"] == k for i in rep["value_issues"])]
    _run_case("T1 フィールドの値の読み戻し", "全欄一致", f"fields {len(fields)} mismatch {mismatch}", not mismatch and len(fields) == rep["fields_created"], rows)

    # T2: 見た目の確認（ラスタ化し、値のある欄の中に描画があるか）。値が見えない欠陥を捕まえる
    ink = field_ink(p("gen.pdf"), d2)
    blank = [k for k, v in ink.items() if data.get(k) and not any(i["id"] == k for i in rep["value_issues"]) and v < 0.002]
    _run_case("T2 欄の値が画面に表示される", "値のある全欄で描画あり", f"ink<0.2%: {blank}", not blank, rows)

    # A1: 再生成側の水平線を 0.5pt ずらす
    d = copy.deepcopy(d2); k = next(i for i, l in enumerate(d["lines"]) if l[0] == "h"); d["lines"][k][1] += 0.5
    fk.generate(d, data, p("a1.pdf")); s = fk.measure(p("orig.pdf"), p("a1.pdf"), d)
    _run_case("A1 罫線1本を0.5ptずらす", "位置誤差max=0.5pt", f"pos {s['lines']['pos']}", abs(s["lines"]["pos"]["max_pt"] - 0.5) < 0.01, rows)

    # A2: 再生成側の罫線を1本欠落させる
    d = copy.deepcopy(d2); del d["lines"][3]
    fk.generate(d, data, p("a2.pdf")); s = fk.measure(p("orig.pdf"), p("a2.pdf"), d)
    _run_case("A2 罫線1本を欠落", "原本にあり再生成に無い≥1", f"missing {s['lines']['missing_in_gen']}", s["lines"]["missing_in_gen"] >= 1, rows)

    # A3: 欄の枠を広げて罫線をまたがせる
    d = copy.deepcopy(d2); f = next(x for x in d["fields"] if x["id"] == "remarks"); f["rect"][3] += 14
    fk.generate(d, data, p("a3.pdf")); s = fk.measure(p("orig.pdf"), p("a3.pdf"), d)
    _run_case("A3 欄が罫線をまたぐ", "罫線干渉≥1", f"interfering {s['fields']['interfering']}", s["fields"]["interfering"] >= 1, rows)

    # A4: 原本が別寸法（595×880、システム生成系に混在する寸法）
    od = dict(orig_def, page_size=[595, 880])
    fk._draw_static(od, p("a4-orig.pdf"), fk.DEFAULT_TTF, flat_values=data)
    s = fk.measure(p("a4-orig.pdf"), p("gen.pdf"), d2)
    _run_case("A4 用紙寸法の違い(595×880)", "寸法差を検出（別版として安全停止）", f"page_size {s['page_size']}", s["page_size"]["d_max_pt"] > 1, rows)

    # A5: 座標未確定の欄
    d = copy.deepcopy(d2); next(x for x in d["fields"] if x["id"] == "address")["coord_status"] = "未確定"
    r = fk.generate(d, data, p("a5.pdf")); names = PdfReader(p("a5.pdf")).get_fields() or {}
    _run_case("A5 座標未確定の欄", "フィールドを作らない", f"skipped {[x['id'] for x in r['fields_skipped']]} in_pdf {'address' in names}",
              "address" not in names and any(x["id"] == "address" for x in r["fields_skipped"]), rows)

    # A6: 備考欄の容量超過
    dd = dict(data, remarks="あ" * 200)
    r = fk.generate(d2, dd, p("a6.pdf")); v = PdfReader(p("a6.pdf")).get_fields()["remarks"].get("/V")
    _run_case("A6 備考の容量超過", "警告を記録し値を入れない（黙って縮小しない）", f"issues {[x['issues'] for x in r['value_issues'] if x['id']=='remarks']} value_len {len(str(v or ''))}",
              any(x["id"] == "remarks" for x in r["value_issues"]) and not v, rows)

    # A7: 固定文字を 1pt ずらす
    d = copy.deepcopy(d2); d["chars"][0]["x"] += 1.0
    fk.generate(d, data, p("a7.pdf")); s = fk.measure(p("orig.pdf"), p("a7.pdf"), d)
    _run_case("A7 固定文字1字を1ptずらす", "文字x誤差max=1.0pt", f"x {s['chars']['x']}", abs(s["chars"]["x"]["max_pt"] - 1.0) < 0.01, rows)

    # A8: 未知の入力形式（写真など）
    d = copy.deepcopy(d2); d["fields"][0]["input_type"] = "写真"
    r = fk.generate(d, data, p("a8.pdf"))
    _run_case("A8 未知の入力形式", "フィールドを作らず理由を記録", f"skipped {r['fields_skipped']}", any("未知" in x["reason"] for x in r["fields_skipped"]), rows)

    # A9: 記号欄に許容外の値
    dd = dict(data, judge_1="良")
    r = fk.generate(d2, dd, p("a9.pdf"))
    _run_case("A9 記号欄に許容外の値", "許容値外として記録", f"issues {[x for x in r['value_issues'] if x['id']=='judge_1']}", any(x["id"] == "judge_1" for x in r["value_issues"]), rows)

    # A10: 線の太さだけ違う（0.5pt → 1.0pt）
    d = copy.deepcopy(d2); d["lines"][0][4] = d["lines"][0][4] + 0.5
    fk.generate(d, data, p("a10.pdf")); s = fk.measure(p("orig.pdf"), p("a10.pdf"), d)
    _run_case("A10 罫線1本の太さ+0.5pt", "太さ誤差max≈0.5pt", f"width {s['lines']['width']}", abs(s["lines"]["width"]["max_pt"] - 0.5) < 0.05, rows)

    # A11: 値はあるが外観（描画）が無い PDF ＝ 初回試作で実際に起きた欠陥（非埋め込みフォントで値が見えない）
    fk.generate(d2, {}, p("a11.pdf"))  # 外観なしの PDF を作り、期待値は data のまま比べる
    ink = field_ink(p("a11.pdf"), d2)
    blank = [k for k, v in ink.items() if data.get(k) and v < 0.002]
    _run_case("A11 欄の値が描画されない", "描画の無い欄を検出", f"検出 {len(blank)} 欄", len(blank) >= 10, rows)

    run_package(outdir, rows)

    with open(p("selftest-results.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case", "expect", "observed", "result"]); w.writeheader(); w.writerows(rows)
    for n in os.listdir(outdir):  # 異常ケースの中間 PDF は残さない（基準の orig/gen のみ残す）
        if n.endswith(".pdf") and n not in ("orig.pdf", "gen.pdf", "package.pdf"):
            os.remove(p(n))
    fails = sum(r["result"] == "FAIL" for r in rows)
    print(f"\n{len(rows) - fails}/{len(rows)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "results", "formkit-selftest")))
