#!/usr/bin/env python3
"""自動火災報知設備点検票（別記様式第11）4型の定義 v0.1/v0.2 を実測から組み立てる
（§4 手順、様式第1・消火器具と同じ方式）。
- その1〜その3: 座標源 = SANKEILOGI戸田【白紙】(Print To PDF 系・配置A)、
  ホールドアウト = ふれあい多居夢 大宮 / 川越（別物件・同一系統）
- 別紙: 座標源 = 大宮（多数派 geometry: 備考下端 215.52、55/75枚）、ホールドアウト = 川越、
  バリアント確認 = SANKEILOGI（備考下端 234.96 の少数派系統）
- 固定文字: 座標源の文字から欄内（=記入）を除いたもの。欄内にある印字ラベルは
  「座標源・両ホールドアウトで同位置・同文字」のものを明示的に戻す。
出力: 定義 v0.1 / v0.2 の候補 JSON とダミーデータ（作業ディレクトリ内）。"""
import json, os, sys, copy
sys.path.insert(0, os.path.expanduser("~/workspace/your_files/yego-repo/tools/formkit"))
import formkit

W = os.path.expanduser("~/workspace/goals/yego/hidden_files/measure-work-jihokai")
MEAS = "実測（2026-11-13、もち・VM内サンプル）: 座標源・ホールドアウト2物件でマス目が一致"

def load(tag):
    return json.load(open(f"{W}/raw/{tag}.json"))

def has_match(ch, pool, tol=1.0):
    return any(p["t"] == ch["t"] and abs(p["x"] - ch["x"]) <= tol and abs(p["y"] - ch["y"]) <= tol
               and abs(p["size"] - ch["size"]) <= 0.6 for p in pool)

def inside(ch, rect):
    return rect[0] - 0.5 <= ch["x"] <= rect[2] + 0.5 and rect[1] - 0.5 <= ch["y"] <= rect[3] + 0.5

def seg_inside(seg, rects):
    o, a, b, c, w = seg
    for (x0, y0, x1, y1) in rects:
        if o == "h" and x0 - 0.5 <= b and c <= x1 + 0.5 and y0 - 0.5 <= a <= y1 + 0.5:
            return True
        if o == "v" and y0 - 0.5 <= b and c <= y1 + 0.5 and x0 - 0.5 <= a <= x1 + 0.5:
            return True
    return False

def form_lines(src, others, judge_rects):
    def clean(d):
        raw = [l for l in d["lines"] if l[4] > 0]
        frag = [l for l in raw if seg_inside(l, judge_rects)]
        fixed = [l for l in raw if not seg_inside(l, judge_rects)]
        return fixed, frag
    fixed, frag = clean(src)
    print(f"  lines: src fixed {len(fixed)}, judge fragments dropped {len(frag)}")
    for name, o in others:
        ofixed, ofrag = clean(o)
        assert ofixed == fixed, f"{name}: 罫線が座標源と一致しない (src {len(fixed)} vs {name} {len(ofixed)})"
        print(f"  lines: {name} fixed {len(ofixed)} == src OK (fragments {len(ofrag)})")
    return fixed

RESTORE_EXCLUDE = []

def build_chars(src, others, fields, restore_filter=None):
    kept, dropped = formkit.filter_chars_outside_fields(src["chars"], fields)
    restored = []
    rects = [f["rect"] for f in fields if f.get("rect")]
    for ch in src["chars"]:
        if not any(inside(ch, r) for r in rects):
            continue
        if any(t == ch["t"] and abs(x - ch["x"]) <= 1.0 and abs(y - ch["y"]) <= 1.0
               for (t, x, y) in RESTORE_EXCLUDE):
            continue
        if restore_filter is not None and not restore_filter(ch):
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

def judge_fields(key, label, y0, y1, cols, rules_out):
    cx, jx, dx, ax = cols
    fs = [
        {"id": f"{key}_content", "label": f"{label} 内容", "input_type": "文字", "layer": "L3",
         "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [cx[0], y0, cx[1], y1]},
        {"id": f"{key}_judge", "label": f"{label} 判定", "input_type": "記号", "layer": "L3",
         "judgment": True, "allowed": ["○", "×", "／"], "capacity": {"max_lines": 1, "max_chars": 1},
         "rect": [jx[0], y0, jx[1], y1],
         "note": "様式の備考3: 正常は○印、不良は×印。／は該当なし（備考6: ※印の欄は自動試験機能を有するものは記入不要で、実帳票では／が記入される)"},
        {"id": f"{key}_defect", "label": f"{label} 不良内容", "input_type": "文字", "layer": "L3",
         "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [dx[0], y0, dx[1], y1]},
        {"id": f"{key}_action", "label": f"{label} 措置内容", "input_type": "文字", "layer": "L3",
         "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [ax[0], y0, ax[1], y1]},
    ]
    rules_out.append({"id": f"{key}-defect-required", "kind": "required_if",
                      "if": {"field": f"{key}_judge", "in": ["×"]}, "then": f"{key}_defect",
                      "reason": "判定が×（不良）のため、不良内容が必須（様式の備考3）"})
    return fs

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

# ================= KOKUJI-11-1（その1） =================
print("=== KOKUJI-11-1")
S1, H1, H12 = load("blank-p10"), load("hold-p12"), load("hold2-p12")
COLS1 = ((206.04, 314.76), (314.76, 354.00), (354.00, 442.56), (442.56, 533.64))
BANDS1 = [(563.88,578.64),(549.12,563.88),(534.72,549.12),(519.96,534.72),(505.56,519.96),(490.80,505.56),
          (476.04,490.80),(461.64,476.04),(446.88,461.64),(432.48,446.88),(417.72,432.48),(402.96,417.72),
          (388.56,402.96),(373.80,388.56),(359.04,373.80),(344.64,359.04),(329.88,344.64),(315.48,329.88),
          (300.72,315.48),(285.96,300.72),(271.56,285.96),(256.80,271.56),(242.40,256.80),(227.64,242.40),
          (212.88,227.64),(198.48,212.88),(183.72,198.48),(168.60,183.72)]
JRECTS1 = [[COLS1[1][0], y0, COLS1[1][1], y1] for (y0, y1) in BANDS1]
lines1 = form_lines(S1, [("hold", H1), ("hold2", H12)], JRECTS1)
ROWS1 = [
    ("battery_exterior", "予備電源・非常電源（内蔵型） 外形"),
    ("battery_display", "予備電源・非常電源（内蔵型） 表示"),
    ("battery_voltage", "予備電源・非常電源（内蔵型） ※端子電圧"),
    ("battery_switch", "予備電源・非常電源（内蔵型） ※切替装置"),
    ("battery_charger", "予備電源・非常電源（内蔵型） ※充電装置"),
    ("battery_wiring", "予備電源・非常電源（内蔵型） ※結線接続"),
    ("rcv_surroundings", "受信機・中継器 周囲の状況"),
    ("rcv_exterior", "受信機・中継器 外形"),
    ("rcv_display", "受信機・中継器 表示"),
    ("rcv_zone_display", "受信機・中継器 警戒区域の表示装置"),
    ("rcv_voltmeter", "受信機・中継器 電圧計"),
    ("rcv_switches", "受信機・中継器 スイッチ類"),
    ("rcv_fuses", "受信機・中継器 ヒューズ類"),
    ("rcv_relay", "受信機・中継器 ※継電器"),
    ("rcv_lamps", "受信機・中継器 表示灯"),
    ("rcv_intercom", "受信機・中継器 通話装置"),
    ("rcv_wiring", "受信機・中継器 ※結線接続"),
    ("rcv_grounding", "受信機・中継器 接地"),
    ("rcv_auxiliary", "受信機・中継器 附属装置"),
    ("rcv_fire_accum", "受信機・中継器 ※火災表示等 蓄積式"),
    ("rcv_fire_analog", "受信機・中継器 ※火災表示等 アナログ式"),
    ("rcv_fire_2signal", "受信機・中継器 ※火災表示等 二信号式"),
    ("rcv_fire_other", "受信機・中継器 ※火災表示等 その他"),
    ("rcv_caution", "受信機・中継器 ※注意表示"),
    ("rcv_circuit", "受信機・中継器 回路導通"),
    ("rcv_temp_setting", "受信機・中継器 設定表示温度等"),
    ("rcv_detector_display", "受信機・中継器 感知器作動等の表示"),
    ("rcv_spares", "受信機・中継器 予備品等"),
]
rules1 = []
fields1 = [
    {"id": "site_name", "label": "名称", "input_type": "文字", "layer": "L2", "source": "物件台帳",
     "capacity": {"max_lines": 1}, "rect": [87.24, 739.56, 380.28, 761.88]},
    {"id": "fire_manager", "label": "防火管理者", "input_type": "文字", "layer": "L2", "source": "物件台帳",
     "capacity": {"max_lines": 1}, "rect": [422.04, 739.56, 533.64, 761.88]},
    {"id": "site_address", "label": "所在", "input_type": "文字", "layer": "L2", "source": "物件台帳",
     "capacity": {"max_lines": 1}, "rect": [87.24, 716.88, 380.28, 739.56]},
    {"id": "witness", "label": "立会者", "input_type": "文字", "layer": "L3", "source": "点検ごとに入力",
     "capacity": {"max_lines": 1}, "rect": [422.04, 716.88, 533.64, 739.56]},
    {"id": "inspect_from", "label": "点検年月日（自）", "input_type": "日付", "layer": "L3",
     "source": "点検ごとに入力", "format": "年・月・日を欄内印字の位置に記入（split_ymd）。和暦・西暦の両方を実帳票で観測",
     "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [246.72, 699.60, 374.90, 716.88],
     "note": "日付欄は「（値）年（値）月（値）日～」の固定スロット並び（実測: 年 x=291.3・月 x=328.1・日 x=364.8・～ x=374.9 が3物件で一致）。矩形は～の手前まで"},
    {"id": "inspect_to", "label": "点検年月日（至）", "input_type": "日付", "layer": "L3",
     "source": "点検ごとに入力", "format": "年・月・日を欄内印字の位置に記入（split_ymd）。和暦・西暦の両方を実帳票で観測",
     "parts": ["year", "month", "day"], "capacity": {"max_lines": 1}, "rect": [384.98, 699.60, 533.64, 716.88],
     "note": "日付欄の～から後ろ"},
    {"id": "inspector_name", "label": "点検者 氏名", "input_type": "選択式", "layer": "L3",
     "allowed": ["（点検者台帳から。台帳は未作成）"], "source": "点検者台帳", "capacity": {"max_lines": 1},
     "rect": [87.24, 654.24, 185.52, 699.60],
     "note": "別記様式第3（点検者一覧表）と同じ台帳を参照する。欄の左上に「氏名」が印字されている（固定文字として復元）"},
    {"id": "company_name_tel", "label": "点検者 所属会社 社名・TEL", "input_type": "固定・自動", "layer": "L2",
     "source": "自社情報", "capacity": {"max_lines": 1}, "rect": [246.72, 676.92, 533.64, 699.60],
     "note": "原本では社名とＴＥＬの間に仕切り線が無く、1セルに連続して記入される（例: 社名に続けてＴＥＬ番号）。分離するかは open_questions"},
    {"id": "company_address", "label": "点検者 所属会社 住所", "input_type": "固定・自動", "layer": "L2",
     "source": "自社情報", "capacity": {"max_lines": 1}, "rect": [246.72, 654.24, 533.64, 676.92]},
    {"id": "receiver_maker", "label": "受信機 製造者名", "input_type": "文字", "layer": "L2", "source": "設備台帳",
     "capacity": {"max_lines": 1}, "rect": [246.72, 637.32, 533.64, 654.24]},
    {"id": "receiver_model", "label": "受信機 型式等", "input_type": "文字", "layer": "L2", "source": "設備台帳",
     "capacity": {"max_lines": 1}, "rect": [246.72, 621.84, 533.64, 637.32],
     "note": "受番号・型式・年製を1欄に連続記入する（原本の記入方式。例: 第○-○号 型式 ○○年製）。「第」は欄内印字として復元。3要素に分割するかは open_questions"},
]
for (key, label), (y0, y1) in zip(ROWS1, BANDS1):
    fields1 += judge_fields(key, label, y0, y1, COLS1, rules1)
fields1 = [F(f) for f in fields1]
defn1 = {
    "form_id": "KOKUJI-11-1", "title": "自動火災報知設備点検票（その１）",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第11（その1）", "family": "設備様式",
    "equipment": "自動火災報知設備", "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=36.48、用紙 595.32×841.92）。42件中: 配置A 34件（+pdf-lib 事前記入版1件が同 geometry）、配置B（全体が x -8.40pt 平行移動）4件、PDFlib 系（用紙 595.44×880.2）2件、近傍（x -0.563pt）1件。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。§4 の手順）。配置A の3物件で罫線が一致（判定印の断片を除く）。詳細は results/jihokai/report.md",
    "$comment": "自動火災報知設備点検票（その１）の帳票定義。v0.2：原本の実測で座標を確定（Microsoft Print To PDF 系・配置A、3物件で照合）",
    "fields": fields1, "rules": rules1,
    "not_fields": [
        {"label": "点検種別（機器・総合）", "reason": "全42件で「機器・総合」が同一位置に印字され値として変動しないため、固定文字として扱う。機器のみ・総合のみの帳票が現れたら欄化が必要（open_questions）"},
        {"label": "点検設備名（受信機）", "reason": "この票の対象設備は受信機で固定。印字済みの見出しとして扱う"},
    ],
    "open_questions": [
        "受信機の型式等欄（受番号・型式・年製）: 原本は1欄に連続記入。台帳の持ち方に合わせて3欄に分割するか",
        "点検種別: 実帳票は全件「機器・総合」。機器点検のみ・総合点検のみの帳票が現れたら欄化が要る",
        "社名・TEL: 原本は仕切り無く1セル。消火器具（KOKUJI-01-1）では仕切り線があり2欄だった。この型は1欄のままにするか",
        "判定の○・／は原本ではベクタ描画（○は曲線、／は罫線状の断片）。再生成では欄の値（文字）として描く前提でよいか（位置の実測は判定欄の矩形で担保）",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3・連動ルール。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "実測で座標を確定（もち、VM 内サンプルで §4 を実施）: 用紙・罫線・固定文字・全欄の rect と coord_status。配置A（多数派）の座標。判定欄の allowed に×と／を設定（備考3・6と実記入から）。点検種別は固定文字扱いと確定"},
    ],
}
print("[KOKUJI-11-1] building chars...")
# 復元から除く「値」の文字（3物件で偶然一致した記入値: 県名・点検者名・電話番号の断片・標準文言の内容記入）
RESTORE_EXCLUDE.extend([
    ("埼", 92, 724), ("玉", 102, 724), ("県", 112, 724),
    ("0", 408, 679), ("-", 443, 679),
    ("山", 112, 668), ("口", 122, 668), ("大", 142, 668), ("介", 152, 668),
    ("ニ", 210, 568), ("ッ", 220, 568),
    ("自", 210, 524), ("動", 220, 524), ("切", 230, 524), ("替", 240, 524),
    ("ト", 210, 509), ("リ", 220, 509), ("ク", 230, 509), ("ル", 240, 509), ("充", 250, 509), ("電", 260, 509),
    ("コ", 210, 494), ("ネ", 220, 494), ("ク", 230, 494), ("タ", 240, 494), ("ー", 250, 494),
    ("1", 210, 480), ("階", 215, 480), ("室", 250, 480), ("内", 260, 480),
    ("P", 210, 465), ("型", 215, 465),
    ("D", 210, 319), ("種", 215, 319), ("接", 225, 319), ("地", 235, 319), ("工", 245, 319), ("事", 255, 319),
])
kept1 = build_chars(S1, [("hold", H1), ("hold2", H12)], fields1)
finish(defn1, S1, kept1, lines1, "KOKUJI-11-1")

# ================= KOKUJI-11-2（その2） =================
print("=== KOKUJI-11-2")
S2, H2, H22 = load("blank-p11"), load("hold-p13"), load("hold2-p13")
COLS2 = ((205.32, 314.40), (314.40, 354.36), (354.36, 444.00), (444.00, 533.28))
BANDS2 = [(767.28,791.04),(743.52,767.28),(719.40,743.52),(695.64,719.40),(671.52,695.64),
          (647.76,671.52),(624.00,647.76),(599.88,624.00),(576.12,599.88),(552.00,576.12),
          (528.24,552.00),(504.48,528.24),(480.36,504.48),(456.60,480.36),(432.48,456.60),
          (408.72,432.48),(384.96,408.72),(360.84,384.96),(337.08,360.84),(312.96,337.08),
          (289.20,312.96),(265.44,289.20),(241.32,265.44),(217.56,241.32),(193.08,217.56)]
JRECTS2 = [[COLS2[1][0], y0, COLS2[1][1], y1] for (y0, y1) in BANDS2]
lines2 = form_lines(S2, [("hold", H2), ("hold2", H22)], JRECTS2)
ROWS2 = [
    ("det_exterior", "感知器 外形"), ("det_zone_uncovered", "感知器 警戒状況 未警戒部分"),
    ("det_zone_coverage", "感知器 警戒状況 感知区域"), ("det_zone_suitability", "感知器 警戒状況 適応性"),
    ("det_zone_obstruction", "感知器 警戒状況 機能障害"), ("det_heat_spot", "熱感知器 スポット型"),
    ("det_heat_dist_air", "熱感知器 ※分布型 空気管式"), ("det_heat_dist_thermo", "熱感知器 ※分布型 熱電対式・熱半導体式"),
    ("det_heat_line", "熱感知器 感知線型"), ("det_smoke_spot", "※煙感知器 スポット型"),
    ("det_smoke_separated", "※煙感知器 分離型"), ("det_flame", "※炎感知器"),
    ("det_multi", "※多信号感知器・複合式感知器"), ("det_remote_test", "遠隔試験機能を有する感知器"),
    ("hatsu_surroundings", "発信機 周囲の状況"), ("hatsu_exterior", "発信機 外形"),
    ("hatsu_display", "発信機 表示"), ("hatsu_button", "発信機 押しボタン・送受話器"),
    ("hatsu_lamp", "発信機 表示灯"), ("sound_exterior", "音響装置 外形"),
    ("sound_mount", "音響装置 取付状態"), ("sound_pressure", "音響装置 音圧等"),
    ("sound_mode", "音響装置 鳴動方式"), ("sound_accum", "音響装置 ※蓄積機能"),
    ("sound_2signal", "音響装置 ※二信号機能"),
]
rules2 = []
fields2 = []
for (key, label), (y0, y1) in zip(ROWS2, BANDS2):
    fields2 += judge_fields(key, label, y0, y1, COLS2, rules2)
fields2 = [F(f) for f in fields2]
defn2 = {
    "form_id": "KOKUJI-11-2", "title": "自動火災報知設備点検票（その２）",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第11（その2）", "family": "設備様式",
    "equipment": "自動火災報知設備", "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=36.48、用紙 595.32×841.92）。42件中の分布はその1と同じ（配置A 34件、配置B 4件、PDFlib 系 2件、pdf-lib 1件、近傍 1件）。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。§4 の手順）。配置A の3物件で罫線が一致（判定印の断片を除く）。その2 に頭の部分（名称・点検年月日等）は無い（原本で確認。表はページ最上部から始まる）。詳細は results/jihokai/report.md",
    "$comment": "自動火災報知設備点検票（その２）の帳票定義。v0.2：原本の実測で座標を確定（Microsoft Print To PDF 系・配置A、3物件で照合）",
    "fields": fields2, "rules": rules2,
    "not_fields": [
        {"label": "頭の部分（名称・点検年月日等）", "reason": "その2 には無い。その1 にのみある（原本で確認）"},
    ],
    "open_questions": [
        "内容欄の選択肢（熱感知器スポット型の差動／定温（再）／熱アナログ、煙感知器スポット型のイオン／光電／アナログ、炎感知器の赤外線／紫外線、鳴動方式の一斉／区分／相互と再鳴動）は、印字された選択肢に○を付す方式（備考4）。選択肢の文字は欄内印字として復元した。選ばれた選択肢を欄の値としてどう持つか（選択式の別欄にするか、内容テキストに含めるか）は機能設計の判断が要る",
        "判定の○・／は原本ではベクタ描画。その1 と同じ論点",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3・連動ルール。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "実測で座標を確定（もち、VM 内サンプルで §4 を実施）: 用紙・罫線・固定文字・全欄の rect と coord_status。配置A（多数派）の座標。その2 に頭の部分が無いことを確認"},
    ],
}
print("[KOKUJI-11-2] building chars...")
RESTORE_EXCLUDE.extend([
    ("A", 209, 345), ("C", 214, 345), ("2", 224, 345), ("4", 229, 345), ("V", 235, 345),
    ("D", 209, 321), ("C", 214, 321), ("2", 224, 321), ("4", 229, 321), ("V", 235, 321),
])
kept2 = build_chars(S2, [("hold", H2), ("hold2", H22)], fields2)
finish(defn2, S2, kept2, lines2, "KOKUJI-11-2")

# ================= KOKUJI-11-3（その3） =================
print("=== KOKUJI-11-3")
S3, H3, H32 = load("blank-p12"), load("hold-p14"), load("hold2-p14")
COLS3 = ((205.32, 314.04), (314.04, 354.00), (354.00, 443.28), (443.28, 534.36))
BANDS3 = [(765.84,791.04),(740.64,765.84),(715.44,740.64),(690.24,715.44),(665.04,690.24),
          (639.48,665.04),(614.64,639.48),(563.16,588.72),(537.60,563.16),(512.40,537.60),(486.84,512.40)]
JRECTS3 = [[COLS3[1][0], y0, COLS3[1][1], y1] for (y0, y1) in BANDS3]
lines3 = form_lines(S3, [("hold", H3), ("hold2", H32)], JRECTS3)
ROWS3 = [
    ("auto_battery", "自動試験機能 予備電源・非常電源"), ("auto_fire_display", "自動試験機能 受信機の火災表示"),
    ("auto_caution_display", "自動試験機能 受信機の注意表示"), ("auto_control", "自動試験機能 受信機・中継器の制御機能・電路"),
    ("auto_detector", "自動試験機能 感知器"), ("auto_circuit", "自動試験機能 感知器回路・ベル回路"),
    ("auto_wireless", "自動試験機能 無線機能"), ("comp_simultaneous", "総合点検 同時作動"),
    ("comp_sensitivity", "総合点検 ※煙感知器等の感度"), ("comp_sound_pressure", "総合点検 地区音響装置の音圧"),
    ("comp_overall", "総合点検 ※総合作動"),
]
rules3 = []
fields3 = []
for (key, label), (y0, y1) in zip(ROWS3, BANDS3):
    fields3 += judge_fields(key, label, y0, y1, COLS3, rules3)
fields3.append({"id": "remarks", "label": "備考", "input_type": "文字", "layer": "L3",
                "source": "点検ごとに入力", "capacity": {"max_lines": 13, "max_chars_per_line": 47},
                "rect": [57.00, 296.76, 534.36, 486.84],
                "note": "備考欄の実寸は 477.36×190.08pt。実帳票の記入は最大1行（42件で観測）。容量は欄の実寸から設定（10.08pt、行高14.04pt で13行、1行47字）"})
MROWS3 = [(1, 262.92, 279.84), (2, 246.00, 262.92), (3, 229.08, 246.00), (4, 212.16, 229.08), (5, 194.52, 212.16)]
MCOLS3 = {"L": {"name": (57.00, 136.20), "model": (136.20, 176.16), "calib": (176.16, 235.20), "maker": (235.20, 294.60)},
          "R": {"name": (295.68, 374.52), "model": (374.52, 414.48), "calib": (414.48, 473.52), "maker": (473.52, 534.36)}}
MCOLJ = {"name": "機器名", "model": "型式", "calib": "校正年月日", "maker": "製造者名"}
for i, y0, y1 in MROWS3:
    for side, colsdef in MCOLS3.items():
        for col, (x0, x1) in colsdef.items():
            fields3.append({"id": f"meter{i}{side}_{col}", "label": f"測定機器 {i}行目{'左' if side=='L' else '右'} {MCOLJ[col]}",
                            "input_type": "文字", "layer": "L2", "source": "自社の測定機器台帳",
                            "capacity": {"max_lines": 1}, "rect": [x0, y0, x1, y1],
                            "note": "機器名（加熱試験器・加煙試験器等）も記入値として扱う（消火器具その2 と同方式）。実帳票では長い型式等が小さい字（9.72〜6.12pt）で記入されることがある。formkit は縮小しない方針"})
fields3 = [F(f) for f in fields3]
defn3 = {
    "form_id": "KOKUJI-11-3", "title": "自動火災報知設備点検票（その３）",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第11（その3）", "family": "設備様式",
    "equipment": "自動火災報知設備", "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=36.48、用紙 595.32×841.92）。42件中の分布はその1と同じ。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。§4 の手順）。配置A の3物件で罫線が一致（判定印の断片を除く）。総合点検は表中の見出し行で区切られる（欄ではない）。詳細は results/jihokai/report.md",
    "$comment": "自動火災報知設備点検票（その３）の帳票定義。v0.2：原本の実測で座標を確定（Microsoft Print To PDF 系・配置A、3物件で照合）",
    "fields": fields3, "rules": rules3,
    "not_fields": [
        {"label": "総合点検の見出し行", "reason": "表の中の見出し行（y 588.72..614.64）。欄ではない"},
        {"label": "頭の部分（名称・点検年月日等）", "reason": "その3 には無い。その1 にのみある（原本で確認）"},
    ],
    "open_questions": [
        "測定機器表は5行×左右で全42件共通か（座標源・ホールドアウト2物件では一致）",
        "判定の○・／は原本ではベクタ描画。その1 と同じ論点",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3・連動ルール。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "実測で座標を確定（もち、VM 内サンプルで §4 を実施）: 用紙・罫線・固定文字・全欄の rect と coord_status。配置A（多数派）の座標。測定機器表は5行×左右と確定"},
    ],
}
print("[KOKUJI-11-3] building chars...")
# 測定機器表（y<280）の欄内文字は全て記入値（自社の機器台帳）なので復元しない
kept3 = build_chars(S3, [("hold", H3), ("hold2", H32)], fields3, restore_filter=lambda ch: ch["y"] > 280)
finish(defn3, S3, kept3, lines3, "KOKUJI-11-3")
print("PART2 DONE")

# ================= JIHOKAI-BESSHI（別紙） =================
print("=== JIHOKAI-BESSHI")
SB, HB = load("hold-p15"), load("hold2-p15")
VARB = load("blank-p13")
BCOLS = [("air", (152.64, 171.00), "空気管式（差動式 ※分布型）"),
         ("thermo", (171.00, 191.16), "熱電対式（差動式 ※分布型）"),
         ("semi", (191.16, 209.88), "熱半導体式（差動式 ※分布型）"),
         ("diff_spot", (209.88, 228.60), "差動式 スポット型"),
         ("fixed_spot", (228.60, 248.04), "定温式 スポット型"),
         ("line", (248.04, 267.48), "※感知線型（定温式）"),
         ("analog", (267.48, 285.84), "熱アナログ式 スポット型"),
         ("ion_nonstor", (285.84, 305.64), "イオン化式 非蓄積（※煙式 スポット型）"),
         ("ion_stor", (305.64, 324.72), "イオン化式 蓄積（※煙式 スポット型）"),
         ("photo_nonstor", (324.72, 343.80), "光電式 非蓄積（※煙式 スポット型）"),
         ("photo_stor", (343.80, 363.96), "光電式 蓄積（※煙式 スポット型）"),
         ("ion_analog", (363.96, 382.32), "イオン化アナログ式（※煙式 スポット型）"),
         ("photo_analog", (382.32, 401.40), "光電アナログ式（※煙式 スポット型）"),
         ("sep_photo_nonstor", (401.40, 421.56), "光電式 非蓄積（※煙式 分離型）"),
         ("sep_photo_stor", (421.56, 440.64), "光電式 蓄積（※煙式 分離型）"),
         ("sep_photo_analog", (440.64, 459.36), "光電アナログ式（※煙式 分離型）")]
ZBANDS = [(628.08,649.68),(606.48,628.08),(584.16,606.48),(562.92,584.16),(542.04,562.92),
          (519.72,542.04),(498.84,519.72),(476.88,498.84),(456.36,476.88),(434.04,456.36),
          (413.52,434.04),(392.28,413.52),(370.68,392.28)]
JRECTSB = [[497.88, y0, 516.60, y1] for (y0, y1) in ZBANDS + [(349.08, 370.68)]]
linesB = form_lines(SB, [("hold2", HB)], JRECTSB)
vfixed = [l for l in VARB["lines"] if l[4] > 0 and not seg_inside(l, JRECTSB)]
only_src = [l for l in linesB if l not in vfixed]
only_var = [l for l in vfixed if l not in linesB]
print(f"  variant SANKEILOGI: lines only in majority {len(only_src)}, only in variant {len(only_var)}")
for l in only_src + only_var:
    print("    DIFF:", l)
BFONT = 10.44
fieldsB = []
for i, (y0, y1) in enumerate(ZBANDS, start=1):
    fieldsB.append({"id": f"zone{i}_no", "label": f"{i}行目 番号", "input_type": "数値", "layer": "L3",
                    "source": "点検ごとに入力（連番）", "capacity": {"max_lines": 1}, "rect": [37.08, y0, 56.52, y1], "font_size": BFONT})
    fieldsB.append({"id": f"zone{i}_name", "label": f"{i}行目 警戒区域名称", "input_type": "文字", "layer": "L3",
                    "source": "物件台帳（警戒区域）", "capacity": {"max_lines": 1}, "rect": [56.52, y0, 152.64, y1], "font_size": BFONT})
    for key, (x0, x1), lab in BCOLS:
        fieldsB.append({"id": f"zone{i}_{key}", "label": f"{i}行目 {lab} 個数", "input_type": "数値", "layer": "L3",
                        "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [x0, y0, x1, y1], "font_size": BFONT})
    fieldsB.append({"id": f"zone{i}_bell", "label": f"{i}行目 地区音響装置 個数", "input_type": "数値", "layer": "L3",
                    "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [459.36, y0, 478.08, y1], "font_size": BFONT})
    fieldsB.append({"id": f"zone{i}_hatsu", "label": f"{i}行目 発信機 個数", "input_type": "数値", "layer": "L3",
                    "source": "点検ごとに入力", "capacity": {"max_lines": 1}, "rect": [478.08, y0, 497.88, y1], "font_size": BFONT})
    fieldsB.append({"id": f"zone{i}_result", "label": f"{i}行目 点検結果", "input_type": "記号", "layer": "L3",
                    "judgment": True, "allowed": ["○", "×", "／"], "capacity": {"max_lines": 1, "max_chars": 1},
                    "rect": [497.88, y0, 516.60, y1], "font_size": BFONT,
                    "note": "様式の備考2: 受信機の表示番号又は警戒区域ごとに個数を記入し、点検結果を記す"})
for key, (x0, x1), lab in BCOLS:
    fieldsB.append({"id": f"total_{key}", "label": f"合計 {lab} 個数", "input_type": "固定・自動", "layer": "L3",
                    "source": "自動集計（各行の合計）", "capacity": {"max_lines": 1}, "rect": [x0, 349.08, x1, 370.68], "font_size": BFONT,
                    "note": "再生成時に各列の合計を自動計算する想定。formkit のルール種別に集計が無いため、定義には計算式を持たない（機能設計の単位）"})
fieldsB.append({"id": "total_bell", "label": "合計 地区音響装置 個数", "input_type": "固定・自動", "layer": "L3",
                "source": "自動集計（各行の合計）", "capacity": {"max_lines": 1}, "rect": [459.36, 349.08, 478.08, 370.68], "font_size": BFONT})
fieldsB.append({"id": "total_hatsu", "label": "合計 発信機 個数", "input_type": "固定・自動", "layer": "L3",
                "source": "自動集計（各行の合計）", "capacity": {"max_lines": 1}, "rect": [478.08, 349.08, 497.88, 370.68], "font_size": BFONT})
fieldsB.append({"id": "remarks", "label": "備考", "input_type": "文字", "layer": "L3",
                "source": "点検ごとに入力", "capacity": {"max_lines": 10, "max_chars_per_line": 44},
                "rect": [56.52, 215.52, 516.60, 349.08], "font_size": BFONT,
                "note": "備考欄の実寸は 460.08×133.56pt（多数派 geometry）。少数派系統（SANKEILOGI 系、14/75枚）では下端が 234.96 で 19.44pt 短い（open_questions）"})
defnB = {
    "form_id": "JIHOKAI-BESSHI", "title": "自動火災報知設備（別紙）感知器の警戒区域別個数表",
    "legal_basis": "平成14年消防庁告示第14号 別記様式第11（別紙）", "family": "設備様式",
    "equipment": "自動火災報知設備", "links": [],
    "lineage": "Microsoft Print To PDF 系・配置A（枠左端 x=37.08、用紙 595.32×841.92）。別紙75枚中: 多数派（備考下端 215.52）55枚、備考下端 234.96 の系統 14枚、PDFlib 系（下端 213.84、行位置も別）2枚、行位置の異なる系統（イニシアイオ）4枚。系統の識別値としての確定は議題2 Q3",
    "geometry_status": "取得済み（2026-11-13、もちが VM 内サンプルで実測。§4 の手順）。多数派 geometry の2物件で罫線が一致。データ域は13行＋合計行で固定（行の高さは行ごとに実測値）。詳細は results/jihokai/report.md",
    "$comment": "自動火災報知設備点検票（別紙）の帳票定義。台帳系（警戒区域ごとに1行、シート数だけ増える）。v0.2：原本の実測で座標を確定（Microsoft Print To PDF 系・配置A 多数派 geometry、2物件で照合）",
    "fields": fieldsB, "rules": [],
    "not_fields": [
        {"label": "合計行の警戒区域名称セル", "reason": "「合計」の印字（固定文字）があるだけのセル。欄は置かない"},
        {"label": "合計行の点検結果セル", "reason": "多数派の系統では無地。欄は置かない（少数派系統では短い横線の断片が観測される。系統差として report に記録）"},
        {"label": "枚数表示（(x/y)）", "reason": "原本の別紙に枚数表示は無い（全75枚で確認）。付けるかは package 生成側の決定事項（消火器管理票と同じ論点）"},
    ],
    "open_questions": [
        "備考欄の高さが系統で異なる（多数派は下端 215.52、SANKEILOGI 系 14/75枚は 234.96 で 19.44pt 短い。備考の見出し文字と下の注記も連動してずれる）。配置B の原点ずらしでは吸収できない（平行移動ではなく高さの差）。系統ごとの扱いは議題2 Q3 の方針に準ずる想定",
        "合計行は自動集計にする想定だが、formkit のルール種別に集計が無い。実装は機能設計の単位",
        "行が13行を超える警戒区域がある物件ではシートが増える（原本は1〜17シート/物件）。シート分割と合計行の置き方（最終シートのみか各シートか）は package 生成側の設計が要る。原本では合計は各シートの最終行に現れる",
    ],
    "changelog": [
        {"version": "0.1", "date": "2026-11-13", "change": "初版（欄の意味・入力形式・L2/L3。座標は全欄未確定）。もちが様式と実記入から構築"},
        {"version": "0.2", "date": "2026-11-13", "change": "実測で座標を確定（もち、VM 内サンプルで §4 を実施）: 用紙・罫線・固定文字・全欄の rect と coord_status。多数派 geometry（備考下端 215.52）の座標。データ域13行＋合計行、感知器16列＋地区音響装置・発信機・点検結果の構成を確定"},
    ],
}
print("[JIHOKAI-BESSHI] building chars...")
# 別紙の欄内文字は全て記入値（区域名・個数）。欄内印字ラベルは無いので復元しない（合計は欄外として残る）
keptB = build_chars(SB, [("hold2", HB)], fieldsB, restore_filter=lambda ch: False)
zone_unmatched = [c for c in keptB if c["y"] > 349.08 and not has_match(c, VARB["chars"])]
print(f"  chars: kept with y>349 (data zone) without SANKEILOGI counterpart: {len(zone_unmatched)}")
for c in zone_unmatched[:20]:
    print("    VAR-UNMATCHED:", c["t"], round(c["x"], 1), round(c["y"], 1))
finish(defnB, SB, keptB, linesB, "JIHOKAI-BESSHI")

# ================= ダミーデータ =================
d1 = {"$comment": "匿名のダミーデータ（実在の物件・人物ではない）",
      "site_name": "試験ビル（ダミー）", "fire_manager": "試験 太郎",
      "site_address": "架空県架空市試験町1-2-3", "witness": "試験 花子",
      "inspect_from": "2026年11月13日", "inspect_to": "2026年11月13日",
      "inspector_name": "試験 太郎",
      "company_name_tel": "架空防災株式会社 TEL 000-0000-0000",
      "company_address": "架空県架空市試験町4-5-6",
      "receiver_maker": "架空防災株式会社", "receiver_model": "第00-0号 RXX-000 2026年製"}
for key, label in ROWS1:
    d1[f"{key}_judge"] = "○"
d1["battery_voltage_content"] = "DC 24V"
d1["rcv_intercom_judge"] = "×"
d1["rcv_intercom_defect"] = "ダミーの不良内容"
d1["rcv_intercom_action"] = "ダミーの措置内容"
d1["rcv_fire_analog_judge"] = "／"
json.dump(d1, open(f"{W}/KOKUJI-11-1.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
d2 = {}
for (key, label) in ROWS2:
    d2[f"{key}_judge"] = "○"
d2["det_heat_spot_content"] = "差動・定温"
d2["sound_mode_content"] = "一斉"
d2["det_flame_judge"] = "／"
json.dump(d2, open(f"{W}/KOKUJI-11-2.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
d3 = {"remarks": "ダミーの備考"}
for (key, label) in ROWS3:
    d3[f"{key}_judge"] = "○"
d3["auto_battery_content"] = "DC 24V"
d3["meter1L_name"] = "加熱試験器"; d3["meter1L_model"] = "HK-3"; d3["meter1L_calib"] = "次期2031,8"; d3["meter1L_maker"] = "保守協会"
d3["meter1R_name"] = "加煙試験器"; d3["meter1R_model"] = "FT-000"; d3["meter1R_calib"] = "次期2033,12"; d3["meter1R_maker"] = "架空防災"
json.dump(d3, open(f"{W}/KOKUJI-11-3.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
dB = {"remarks": "ダミーの備考"}
for i in (1, 2, 3):
    dB[f"zone{i}_no"] = str(i); dB[f"zone{i}_name"] = f"{i}階"
    dB[f"zone{i}_diff_spot"] = "10"; dB[f"zone{i}_fixed_spot"] = "8"; dB[f"zone{i}_photo_nonstor"] = "2"
    dB[f"zone{i}_bell"] = "1"; dB[f"zone{i}_hatsu"] = "1"; dB[f"zone{i}_result"] = "○"
dB["total_diff_spot"] = "30"; dB["total_fixed_spot"] = "24"; dB["total_photo_nonstor"] = "6"
dB["total_bell"] = "3"; dB["total_hatsu"] = "3"
json.dump(dB, open(f"{W}/JIHOKAI-BESSHI.dummy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ALL DONE")
