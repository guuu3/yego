#!/usr/bin/env python3
"""別記様式第2（点検結果総括表）・別記様式第3（点検者一覧表）の定義 v0.1/v0.2 を
実測から組み立てる（§4 手順、様式第1・消火器具・自火報と同じ方式）。
- 座標源 = SANKEILOGI戸田【白紙】(Print To PDF 系・配置A、総括表 p2／一覧表 p3）
- ホールドアウト = ふれあい多居夢 大宮 / 川越（別物件・同一系統）
- 固定文字: 座標源の文字から欄内（=記入）を除いたもの。欄内にある印字ラベルは
  「座標源・両ホールドアウトで同位置・同文字」のものだけを、欄ごとに許可した
  ラベル文字に限って戻す（設備名・住所・氏名など値そのものは戻さない）。
出力: 定義 v0.1 / v0.2 の候補 JSON とダミーデータ（作業ディレクトリ内）。"""
import json, os, sys, copy
sys.path.insert(0, os.path.expanduser("~/workspace/your_files/yego-repo/tools/formkit"))
import formkit

W = os.path.expanduser("~/workspace/goals/yego/hidden_files/measure-work-yoshiki23")

def load(tag):
    return json.load(open(f"{W}/raw/{tag}.json"))

def has_match(ch, pool, tol=1.0):
    return any(p["t"] == ch["t"] and abs(p["x"] - ch["x"]) <= tol and abs(p["y"] - ch["y"]) <= tol
               and abs(p["size"] - ch["size"]) <= 0.6 for p in pool)

def inside(ch, rect):
    return rect[0] - 0.5 <= ch["x"] <= rect[2] + 0.5 and rect[1] - 0.5 <= ch["y"] <= rect[3] + 0.5

def form_lines(src, others):
    fixed = [l for l in src["lines"] if l[4] > 0]
    print(f"  lines: src fixed {len(fixed)} (w=0 の用紙端 {len(src['lines']) - len(fixed)} 本を除外)")
    for name, o in others:
        ofixed = [l for l in o["lines"] if l[4] > 0]
        assert ofixed == fixed, f"{name}: 罫線が座標源と一致しない (src {len(fixed)} vs {name} {len(ofixed)})"
        print(f"  lines: {name} fixed {len(ofixed)} == src OK")
    return fixed

def build_chars(src, others, fields, restore_ok):
    kept, dropped = formkit.filter_chars_outside_fields(src["chars"], fields)
    restored = []
    for f in fields:
        if not f.get("rect"):
            continue
        for ch in src["chars"]:
            if not inside(ch, f["rect"]):
                continue
            if not restore_ok(f, ch):
                continue
            if all(has_match(ch, o["chars"]) for _, o in others):
                restored.append(ch)
    print(f"  chars: total {len(src['chars'])}, outside-fields kept {len(kept)}, in-field labels restored {len(restored)}")
    for c in sorted(restored, key=lambda c: (-c["y"], c["x"])):
        print("    RESTORED:", c["t"], round(c["x"], 1), round(c["y"], 1))
    kept = kept + restored
    for name, o in others:
        unmatched = [c for c in kept if not has_match(c, o["chars"])]
        print(f"  chars: kept {len(kept)}, without counterpart in {name}: {len(unmatched)}")
        for c in unmatched[:20]:
            print("    UNMATCHED:", c["t"], round(c["x"], 1), round(c["y"], 1))
    return kept

def vocab_of(kept):
    rows = {}
    for ch in kept:
        rows.setdefault(round(ch["y"]), []).append(ch)
    return ["".join(c["t"] for c in sorted(rows[y], key=lambda c: c["x"])) for y in sorted(rows, reverse=True)]

def finish(defn, src, kept, lines, tag):
    defn["version"] = "0.2"
    defn["page_size"] = src["page_size"]
    defn["lines"] = lines
    defn["chars"] = [{"t": c["t"], "x": c["x"], "y": c["y"], "size": c["size"]} for c in kept]
    defn["fixed_text_vocabulary"] = vocab_of(kept)
    for f in defn["fields"]:
        if f.get("rect"):
            f["coord_status"] = "確定"
    errs = formkit.validate_definition(defn)
    print(f"[{tag}] validate: {errs or 'OK'}")
    out = f"{W}/{tag}.v0.2.candidate.json"
    json.dump(defn, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d1 = copy.deepcopy(defn)
    d1["version"] = "0.1"
    d1["page_size"] = None
    d1["page_size_candidates"] = [[595, 842], [595, 880]]
    d1["geometry_status"] = "未取得（原本 PDF の実測前。docs/forms/yoshiki1-first-run.md §4 と同じ手順で取る）"
    d1["lineage"] = "未識別（系統の識別値は議題2 Q3 で未決）"
    d1["lines"] = []
    d1["chars"] = []
    d1["$comment"] = defn["$comment"].replace("v0.2：", "初版。") + "座標は全欄『未確定』で、生成器はフィールドを作らない。"
    d1["changelog"] = [c for c in defn["changelog"] if c["version"] == "0.1"]
    for f in d1["fields"]:
        f["rect"] = None
        f["coord_status"] = "未確定"
        f.pop("font_size", None)
    json.dump(d1, open(f"{W}/{tag}.v0.1.candidate.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[{tag}] candidates written (fields {len(defn['fields'])}, confirmed {sum(1 for f in defn['fields'] if f.get('coord_status')=='確定')})")

FONT = 10.08
def F(f):
    f.setdefault("font_size", FONT)
    return f

# ================= BEKKI-2（点検結果総括表 その1） =================
print("=== BEKKI-2")
S2, H2, H22 = load("src-p2"), load("hold-p2"), load("hold2-p2")
lines2 = form_lines(S2, [("hold", H2), ("hold2", H22)])

ROWS2 = [(442.2, 500.52), (383.88, 442.2), (325.56, 383.88),
         (267.6, 325.56), (209.28, 267.6), (150.96, 209.28)]
fields2 = [
    F({"id": "site_name", "label": "名称", "input_type": "文字", "layer": "L2", "source": "物件台帳",
       "capacity": {"max_lines": 1}, "rect": [93.72, 698.16, 288.84, 767.64]}),
    F({"id": "fire_manager", "label": "防火管理者", "input_type": "文字", "layer": "L2", "source": "物件台帳",
       "capacity": {"max_lines": 1}, "rect": [347.16, 698.16, 533.64, 767.64]}),
    F({"id": "site_address", "label": "所在地", "input_type": "文字", "layer": "L2", "source": "物件台帳",
       "capacity": {"max_lines": 1}, "rect": [93.72, 628.32, 288.84, 698.16]}),
    F({"id": "inspection_supervisor", "label": "点検実施責任者", "input_type": "文字", "layer": "L3",
       "source": "点検者台帳", "capacity": {"max_lines": 2}, "rect": [347.16, 628.32, 533.64, 698.16],
       "note": "社名＋責任者名を記入（実帳票では2行の例あり）"}),
    F({"id": "inspect_type", "label": "点検種別", "input_type": "選択式", "layer": "L3",
       "allowed": ["機器点検", "総合点検", "設備等設置維持計画による点検"],
       "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [93.72, 577.92, 226.2, 628.32],
       "note": "選択肢（機器点検・総合点検・（設備等設置維持計画による点検））が欄内に印字され、"
               "該当するものに○を付す（原本ではベクタの楕円）。値は選択した種別。印字文は固定文字として復元"}),
    F({"id": "inspect_from", "label": "点検年月日（自）", "input_type": "日付", "layer": "L3",
       "source": "点検ごとに入力", "format": "年・月・日を欄内印字の位置に記入（split_ymd）",
       "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [288.84, 577.92, 406.2, 628.32],
       "note": "実測: スロット 年 x=325.6・月 x=360.5・日 x=394.3（3物件で一致）。矩形は～の手前まで"}),
    F({"id": "inspect_to", "label": "点検年月日（至）", "input_type": "日付", "layer": "L3",
       "source": "点検ごとに入力", "format": "年・月・日を欄内印字の位置に記入（split_ymd）",
       "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [416.28, 577.92, 533.64, 628.32],
       "note": "実測: ～ x=406.2、至のスロット 年 x=451.2・月 x=485.4・日 x=519.6"}),
]
rules2 = []
for i, (y0, y1) in enumerate(ROWS2, start=1):
    k = f"row{i}"
    fields2 += [
        F({"id": f"{k}_equip", "label": f"{i}行目 設備名", "input_type": "文字", "layer": "L2",
           "source": "物件台帳", "capacity": {"max_lines": 2}, "rect": [36.84, y0, 139.8, y1]}),
        F({"id": f"{k}_judge", "label": f"{i}行目 判定", "input_type": "選択式", "layer": "L3",
           "judgment": True, "allowed": ["良", "不良"], "source": "点検ごとに入力",
           "capacity": {"max_lines": 1, "max_chars": 2}, "rect": [139.8, y0, 208.2, y1],
           "note": "様式の備考2: 正常の場合は「良」に、不良の場合は「不良」に○印を付す"
                   "（原本ではベクタの楕円）。欄内に「良・不良」が印字され固定文字として復元"}),
        F({"id": f"{k}_defect", "label": f"{i}行目 不良内容", "input_type": "文字", "layer": "L3",
           "source": "点検ごとに入力", "capacity": {"max_lines": 3}, "rect": [208.2, y0, 288.84, y1]}),
        F({"id": f"{k}_action", "label": f"{i}行目 措置内容", "input_type": "文字", "layer": "L3",
           "source": "点検ごとに入力", "capacity": {"max_lines": 3}, "rect": [288.84, y0, 410.52, y1]}),
        F({"id": f"{k}_witness", "label": f"{i}行目 立会者", "input_type": "文字", "layer": "L3",
           "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [410.52, y0, 533.64, y1]}),
    ]
    rules2.append({"id": f"{k}-defect-required", "kind": "required_if",
                   "if": {"field": f"{k}_judge", "in": ["不良"]}, "then": f"{k}_defect",
                   "reason": "判定が不良のため、不良内容が必須（様式の備考2）"})

def restore2(f, ch):
    if f["id"] == "inspect_type":
        return True
    if f["id"] in ("inspect_from", "inspect_to"):
        return ch["t"] in "年月日"
    if f["id"].endswith("_judge"):
        return ch["t"] in "良不良・"
    return False

kept2 = build_chars(S2, [("hold", H2), ("hold2", H22)], fields2, restore2)
defn2 = {
    "form_id": "BEKKI-2",
    "title": "消防用設備等（特殊消防用設備等）点検結果総括表（その１）",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第2",
    "family": "共通様式",
    "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=36.84。用紙 595.32×841.92）。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。docs/forms/yoshiki1-first-run.md §4 の手順）。"
                       "配置A の3物件で罫線が完全一致。全数センサス（55件）: 配置A 43件／配置B（x −8.40pt）7件／"
                       "PDFlib 系 4件／近傍（pdf-lib、−0.56pt）1件。詳細は results/yoshiki23/report.md",
    "$comment": "別記様式第2（点検結果総括表（その１））の帳票定義。v0.2：原本の実測で座標を確定"
                "（Microsoft Print To PDF 系・配置A、3物件で照合）。",
    "fields": fields2,
    "rules": rules2,
    "not_fields": [],
    "open_questions": [
        "総括表（その2）: サンプル55件すべて（その１）のみで、その2 は観測されなかった。設備行が6行を超える物件でその2 が使われる可能性は残る",
        "点検種別: 機器点検と総合点検の両方を実施した場合に両方へ○が付く運用があり得る。現行の選択式は単一選択のため、実帳票で複数選択の例が現れたら欄の持ち方の見直しが要る",
        "判定の○は原本ではベクタの楕円。再生成では選択式の値（良／不良）として保持し、楕円そのものは描かない（他の様式の○印と同じ扱い）",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3・連動ルール。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "原本の実測で全欄の座標を確定（配置A、座標源＋ホールドアウト2物件で照合）"},
    ],
    "version": "0.2",
    "page_size": None,
    "lines": [], "chars": [], "fixed_text_vocabulary": [],
}
finish(defn2, S2, kept2, lines2, "BEKKI-2")

dummy2 = {"$comment": "BEKKI-2 再生成テスト用の匿名ダミーデータ（実データではない）",
          "site_name": "試験ビル（ダミー）", "fire_manager": "試験 太郎",
          "site_address": "試験県試験市試験1丁目1-1", "inspection_supervisor": "試験点検株式会社 試験 太郎",
          "inspect_type": "機器点検", "inspect_from": "2026年11月13日", "inspect_to": "2026年11月13日"}
for i in range(1, 7):
    dummy2[f"row{i}_equip"] = f"試験設備{i}（ダミー）"
    dummy2[f"row{i}_judge"] = "良"
    dummy2[f"row{i}_witness"] = "試験 立会"
json.dump(dummy2, open(f"{W}/BEKKI-2.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("[BEKKI-2] dummy written")

# ================= BEKKI-3（点検者一覧表） =================
print("=== BEKKI-3")
S3, H3, H32 = load("src-p3"), load("hold-p3"), load("hold2-p3")
lines3 = form_lines(S3, [("hold", H3), ("hold2", H32)])

SHIKAKU_ROWS = [
    ("tokurui", "甲種 特類", False, (697.44, 712.92)),
    ("k1", "甲・乙種 1類", True, (681.96, 697.44)),
    ("k2", "甲・乙種 2類", True, (666.48, 681.96)),
    ("k3", "甲・乙種 3類", True, (651.0, 666.48)),
    ("k4", "甲・乙種 4類", True, (635.52, 651.0)),
    ("k5", "甲・乙種 5類", True, (620.04, 635.52)),
    ("o6", "乙種 6類", False, (604.56, 620.04)),
    ("o7", "乙種 7類", False, (589.08, 604.56)),
]
KAKUSHA_ROWS = [
    ("tokushu", "特種", (527.16, 542.64)),
    ("d1", "第1種", (511.68, 527.16)),
    ("d2", "第2種", (496.56, 511.68)),
]
DATE_FMT = "元号の頭文字（H・R 等）＋年・月・日を欄内印字の位置に記入（split_ymd）"
fields3 = []
for b, off in ((1, 0.0), (2, -305.28)):
    p = f"b{b}_"
    fields3 += [
        F({"id": f"{p}equipments", "label": f"点検者{b} 設備名", "input_type": "文字", "layer": "L2",
           "source": "物件台帳", "capacity": {"max_lines": 12},
           "rect": [392.16, 496.56 + off, 530.04, 774.84 + off],
           "note": "その点検者が担当する設備名を列記する欄（実帳票では1行に1設備）"}),
        F({"id": f"{p}inspector_address", "label": f"点検者{b} 住所", "input_type": "文字", "layer": "L3",
           "source": "点検者台帳", "capacity": {"max_lines": 1}, "rect": [89.4, 759.36 + off, 243.84, 774.84 + off]}),
        F({"id": f"{p}inspector_name", "label": f"点検者{b} 氏名", "input_type": "選択式", "layer": "L3",
           "allowed": ["（点検者台帳から。台帳は未作成）"], "source": "点検者台帳",
           "capacity": {"max_lines": 1}, "rect": [297.12, 759.36 + off, 392.16, 774.84 + off],
           "note": "他の様式の点検者氏名と同じ台帳を参照する"}),
        F({"id": f"{p}company", "label": f"点検者{b} 社名", "input_type": "文字", "layer": "L3",
           "source": "点検者台帳", "capacity": {"max_lines": 1}, "rect": [89.4, 743.88 + off, 243.84, 759.36 + off]}),
        F({"id": f"{p}tel", "label": f"点検者{b} 電話番号", "input_type": "文字", "layer": "L3",
           "source": "点検者台帳", "capacity": {"max_lines": 1}, "rect": [297.12, 743.88 + off, 392.16, 759.36 + off]}),
    ]
    for key, label, has_sel, (y0, y1) in SHIKAKU_ROWS:
        y0, y1 = y0 + off, y1 + off
        base = f"{p}g_{key}"
        if has_sel:
            fields3.append(F({"id": f"{base}_class", "label": f"点検者{b} 消防設備士 {label} 甲乙の別",
                              "input_type": "選択式", "layer": "L3", "allowed": ["甲", "乙"],
                              "source": "点検者台帳", "capacity": {"max_lines": 1, "max_chars": 1},
                              "rect": [36.12, y0, 89.76, y1],
                              "note": "印字された「甲・乙種」の該当する方に○を付す（原本ではベクタの楕円）。値は甲または乙"}))
        fields3 += [
            F({"id": f"{base}_issue_date", "label": f"点検者{b} 消防設備士 {label} 交付年月日",
               "input_type": "日付", "layer": "L3", "source": "点検者台帳", "format": DATE_FMT,
               "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [121.8, y0, 211.08, y1]}),
            F({"id": f"{base}_issue_no", "label": f"点検者{b} 消防設備士 {label} 交付番号",
               "input_type": "文字", "layer": "L3", "source": "点検者台帳",
               "capacity": {"max_lines": 1}, "rect": [211.08, y0, 270.84, y1],
               "note": "欄内に「第」「号」が印字され、その間に番号を記入（印字は固定文字として復元）"}),
            F({"id": f"{base}_governor", "label": f"点検者{b} 消防設備士 {label} 交付知事",
               "input_type": "文字", "layer": "L3", "source": "点検者台帳",
               "capacity": {"max_lines": 1}, "rect": [270.84, y0, 323.76, y1]}),
            F({"id": f"{base}_course_ym", "label": f"点検者{b} 消防設備士 {label} 講習受講年月",
               "input_type": "日付", "layer": "L3", "source": "点検者台帳",
               "format": "元号の頭文字（H・R 等）＋年・月を欄内印字の位置に記入（split_ymd）",
               "parts": ["year", "month"], "capacity": {"max_lines": 1}, "rect": [323.76, y0, 392.16, y1]}),
        ]
    fields3.append(F({"id": f"{p}shikaku_note", "label": f"点検者{b} 備考", "input_type": "文字", "layer": "L3",
                      "source": "点検者台帳", "capacity": {"max_lines": 1},
                      "rect": [121.8, 573.6 + off, 392.16, 589.08 + off],
                      "note": "様式の備考4: 誘導灯及び誘導標識の点検を実施した者は、電気工事士免状等の種類・交付番号・交付年月日を記載する"}))
    for key, label, (y0, y1) in KAKUSHA_ROWS:
        y0, y1 = y0 + off, y1 + off
        base = f"{p}k_{key}"
        fields3 += [
            F({"id": f"{base}_issue_date", "label": f"点検者{b} 消防設備点検資格者 {label} 交付年月日",
               "input_type": "日付", "layer": "L3", "source": "点検者台帳", "format": DATE_FMT,
               "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [121.8, y0, 211.44, y1]}),
            F({"id": f"{base}_issue_no", "label": f"点検者{b} 消防設備点検資格者 {label} 交付番号",
               "input_type": "文字", "layer": "L3", "source": "点検者台帳",
               "capacity": {"max_lines": 1}, "rect": [211.44, y0, 301.8, y1],
               "note": "欄内に「第」「号」が印字され、その間に番号を記入（印字は固定文字として復元）"}),
            F({"id": f"{base}_expiry", "label": f"点検者{b} 消防設備点検資格者 {label} 有効期限",
               "input_type": "日付", "layer": "L3", "source": "点検者台帳", "format": DATE_FMT,
               "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [301.8, y0, 392.16, y1]}),
        ]

def restore3(f, ch):
    fid = f["id"]
    if fid.endswith("_class"):
        return True
    if fid.endswith("_issue_date") or fid.endswith("_expiry"):
        return ch["t"] in "年月日"
    if fid.endswith("_course_ym"):
        return ch["t"] in "年月"
    if fid.endswith("_issue_no"):
        return ch["t"] in "第号"
    return False

kept3 = build_chars(S3, [("hold", H3), ("hold2", H32)], fields3, restore3)
defn3 = {
    "form_id": "BEKKI-3",
    "title": "消防用設備等（特殊消防用設備等）点検者一覧表",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第3",
    "family": "共通様式",
    "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=36.12。用紙 595.32×841.92）。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。docs/forms/yoshiki1-first-run.md §4 の手順）。"
                       "配置A の3物件で罫線が完全一致。全数センサス（55件）: 配置A 43件／配置B（x −8.40pt）7件／"
                       "PDFlib 系 4件／近傍（pdf-lib、−0.56pt）1件（様式第2 と同一の分布）。詳細は results/yoshiki23/report.md",
    "$comment": "別記様式第3（点検者一覧表）の帳票定義。v0.2：原本の実測で座標を確定"
                "（Microsoft Print To PDF 系・配置A、3物件で照合）。",
    "fields": fields3,
    "rules": [],
    "not_fields": [
        {"label": "消防設備点検資格者の保持を示す○印", "reason": "特種・第1種・第2種の行に付けられる楕円は保持の表示で、交付年月日・交付番号の記入と重なる情報のため欄にしない"},
        {"label": "点検者ブロックの3人目以降", "reason": "1枚に2人分。3人目以降は次シートに続く（台帳系のシート増。枚数表示の扱いは別記様式第11 別紙と同じく原本に表示なし）"},
    ],
    "open_questions": [
        "点検者台帳の形: 氏名は他の様式と同じく選択式（台帳参照）とした。台帳そのものの設計は機能設計側（バトンの申し送り）",
        "設備名欄: 値が複数行になる（1行1設備）。formkit の複数行の値が落ちる既知の不具合に当たるため、生成時の扱いは申し送り参照",
        "消防設備士の甲乙の別: 甲・乙種1〜5類のみ欄にした。特類（甲種のみ）・6・7類（乙種のみ）は印字で確定するため欄なし",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "原本の実測で全欄の座標を確定（配置A、座標源＋ホールドアウト2物件で照合）"},
    ],
    "version": "0.2",
    "page_size": None,
    "lines": [], "chars": [], "fixed_text_vocabulary": [],
}
finish(defn3, S3, kept3, lines3, "BEKKI-3")

dummy3 = {"$comment": "BEKKI-3 再生成テスト用の匿名ダミーデータ（実データではない）",
          "b1_equipments": "試験設備（ダミー）", "b1_inspector_address": "試験県試験市試験1丁目1-1",
          "b1_inspector_name": "試験 太郎", "b1_company": "試験点検株式会社", "b1_tel": "00-0000-0000",
          "b1_g_k1_class": "甲", "b1_g_k1_issue_date": "H31年3月18日", "b1_g_k1_issue_no": "00211",
          "b1_g_k1_governor": "試験県", "b1_g_k1_course_ym": "R7年12月",
          "b1_k_d1_issue_date": "R5年1月30日", "b1_k_d1_issue_no": "142802612", "b1_k_d1_expiry": "R10年3月31日",
          "b2_inspector_name": "試験 太郎"}
json.dump(dummy3, open(f"{W}/BEKKI-3.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("[BEKKI-3] dummy written")
print("ALL DONE")
