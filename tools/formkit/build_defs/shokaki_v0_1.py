"""消火器具の型（点検票 その1・その2、消火器管理票）の帳票定義 v0.1 を作る。

根拠:
- 点検票の様式：消防用設備等の点検要領に基づく点検票の告示（平成14年消防庁告示第14号）別記様式第1
  「消火器具点検票」（その1・その2）。※規則の別記様式第1（点検結果報告書＝BEKKI-1）とは別物。番号が同じなので
  ID は KOKUJI-01-1 / KOKUJI-01-2 とし、legal_basis で出典を区別する
- 欄の並び：実帳票1物件のテキスト層で確認（2026-11-11、Google ドライブ上。記入値はリポジトリに入れていない）。
  系統・版の違いは未確認（1物件のみ）
- 座標：原本の実測前のため全欄「未確定」。生成器はフィールドを作らない（編集禁止）

実行: python3 build_defs/shokaki_v0_1.py  （forms/definitions/shokaki/ に書き出す）
"""
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(REPO, "forms", "definitions", "shokaki")
KINDS = ["A", "B", "C", "D", "E", "F"]  # Ａ粉末 Ｂ泡 Ｃ強化液 Ｄ二酸化炭素 Ｅハロゲン化物 Ｆ水
KIND_NAMES = {"A": "粉末消火器", "B": "泡消火器", "C": "強化液消火器", "D": "二酸化炭素消火器", "E": "ハロゲン化物消火器", "F": "水消火器"}


def U(**k):
    return dict(coord_status="未確定", rect=None, **k)


def header(prefix_note):
    """点検票の頭の部分（その1・その2 共通の構成。その2 に頭があるかは原本で要確認）。"""
    return [
        U(id="site_name", label="名称", input_type="文字", layer="L2", capacity={"max_lines": 1}, source="物件台帳"),
        U(id="fire_manager", label="防火管理者", input_type="文字", layer="L2", capacity={"max_lines": 1}, source="物件台帳"),
        U(id="site_address", label="所在", input_type="文字", layer="L2", capacity={"max_lines": 1}, source="物件台帳"),
        U(id="witness", label="立会者", input_type="文字", layer="L3", capacity={"max_lines": 1}, source="点検ごとに入力"),
        U(id="inspect_from", label="点検年月日（自）", input_type="日付", layer="L3", format="年・月・日を別々のマスに記入（split_ymd）",
          parts=["year", "month", "day"], source="点検ごとに入力"),
        U(id="inspect_to", label="点検年月日（至）", input_type="日付", layer="L3", format="split_ymd",
          parts=["year", "month", "day"], source="点検ごとに入力"),
        U(id="inspector_name", label="点検者 氏名", input_type="選択式", layer="L3",
          allowed=["（点検者台帳から。台帳は未作成）"], source="点検者台帳", note="別記様式第3（点検者一覧表）と同じ台帳を参照する"),
        U(id="company_name", label="点検者 所属会社 社名", input_type="固定・自動", layer="L2", source="自社情報"),
        U(id="company_tel", label="点検者 所属会社 TEL", input_type="固定・自動", layer="L2", source="自社情報"),
        U(id="company_address", label="点検者 所属会社 住所", input_type="固定・自動", layer="L2", source="自社情報"),
    ]


def item_rows(items):
    """点検項目の行：種別 A〜F（該当に○）、判定（○ または不良個数）、不良内容、措置内容。"""
    fields, rules = [], []
    for key, label in items:
        for k in KINDS:
            fields.append(U(id=f"{key}_kind_{k}", label=f"{label} 種別{k}（{KIND_NAMES[k]}）", input_type="記号", layer="L3",
                            allowed=["○"], source="点検ごとに入力（設置されている種別に○）"))
        fields.append(U(id=f"{key}_judge", label=f"{label} 判定", input_type="記号", layer="L3", judgment=True,
                        allowed=["○", "／"], allowed_count={"min": 1, "max": 999},
                        note="様式の備考3：正常は○、不良は不良個数を記入。「／」（該当なし）を許すかは実帳票で要確認"))
        fields.append(U(id=f"{key}_defect", label=f"{label} 不良内容", input_type="文字", layer="L3", capacity={"max_lines": 1}))
        fields.append(U(id=f"{key}_action", label=f"{label} 措置内容", input_type="文字", layer="L3", capacity={"max_lines": 1},
                        note="措置内容は空欄を原則とする（Gate A Q10）"))
        rules.append({"id": f"{key}-defect-required", "kind": "required_if",
                      "if": {"field": f"{key}_judge", "in": [], "count": True}, "then": f"{key}_defect",
                      "reason": "不良個数が記入されたため、不良内容が必須（様式の備考3）"})
    return fields, rules


SONO1_ITEMS = [  # 機器点検：設置状況・消火器の外形
    ("place", "設置場所"), ("interval", "設置間隔"), ("suitability", "適応性"), ("seismic", "耐震措置"), ("sign", "表示・標識"),
    ("body", "本体容器"), ("pin_seal", "安全栓の封"), ("pin", "安全栓"), ("used_indicator", "使用済みの表示装置"),
    ("lever", "押し金具・レバー等"), ("cap", "キャップ"), ("hose", "ホース"), ("nozzle", "ノズル・ホーン・ノズル栓"),
    ("gauge", "指示圧力計"), ("regulator", "圧力調整器"), ("safety_valve", "安全弁"), ("holder", "保持装置"),
    ("wheel", "車輪（車載式）"), ("gas_tube", "ガス導入管（車載式）"),
]
SONO2_ITEMS = [  # 機器点検：消火器の内部等・機能、簡易消火用具
    ("int_body", "本体容器（内部）"), ("int_inner", "内筒等"), ("int_level", "液面表示"),
    ("agent_state", "消火薬剤 性状"), ("agent_amount", "消火薬剤量"), ("gas_cylinder", "加圧用ガス容器"),
    ("cutter", "カッター・押し金具"), ("int_hose", "ホース（内部等）"), ("open_nozzle", "開閉式ノズル・切替式ノズル"),
    ("int_gauge", "指示圧力計（内部等）"), ("int_used_indicator", "使用済みの表示装置（内部等）"),
    ("int_regulator", "圧力調整器（内部等）"), ("relief", "安全弁・減圧孔（排圧栓を含む。）"), ("powder_seal", "粉上り防止用封板"),
    ("packing", "パッキン"), ("siphon", "サイホン管・ガス導入管"), ("strainer", "ろ過網"),
    ("discharge", "放射能力"), ("pressure_test", "消火器の耐圧性能"),
    ("simple_exterior", "簡易消火用具 外形"), ("simple_water", "簡易消火用具 水量等"),
]

NOTES_COMMON = [
    "この用紙の大きさは、日本産業規格Ａ４とすること。",
    "消火器の種別欄は、該当するものについて記入すること。Ａは粉末消火器、Ｂは泡消火器、Ｃは強化液消火器、Ｄは二酸化炭素消火器、Ｅはハロゲン化物消火器、Ｆは水消火器をいう。",
    "判定欄は、正常の場合は○印、不良の場合は不良個数を記入し、不良内容欄にその内容を記入すること。",
    "選択肢のある欄は、該当事項に○印を付すこと。",
    "措置内容欄には、点検の際措置した内容を記入すること。",
]


def base(form_id, title, legal, family):
    return {
        "form_id": form_id, "title": title, "version": "0.1", "legal_basis": legal, "family": family,
        "lineage": "未識別（系統の識別値は議題2 Q3 で未決。観察は1物件のみ）",
        "page_size": None, "page_size_candidates": [[595, 842], [595, 880]],
        "geometry_status": "未取得（原本 PDF の実測前。docs/forms/yoshiki1-first-run.md §4 と同じ手順で取る）",
        "lines": [], "chars": [], "links": [],
        "changelog": [{"version": "0.1", "date": "2026-11-12", "change": "初版（欄の意味・入力形式・L2/L3・連動ルール。座標は全欄未確定）"}],
    }


def build():
    os.makedirs(OUT, exist_ok=True)
    out = {}

    f1, r1 = item_rows(SONO1_ITEMS)
    d1 = base("KOKUJI-01-1", "消火器具点検票（その１）", "平成14年消防庁告示第14号 別記様式第1（その1）", "設備様式")
    d1["$comment"] = "消火器具点検票（その１）の帳票定義 初版。座標は全欄『未確定』で、生成器はフィールドを作らない。"
    d1["fixed_text_vocabulary"] = ["別記様式第１", "（その１）", "消火器具点検票", "名称", "防火管理者", "所在", "立会者", "点検種別",
                                   "機器点検", "点検年月日", "点検者", "氏名", "所属会社", "社名", "ＴＥＬ", "住所", "点検項目", "点検結果",
                                   "消火器の種別", "判定", "不良内容", "措置内容", "設置状況", "消火器の外形"] + [l for _, l in SONO1_ITEMS] + NOTES_COMMON
    d1["fields"] = header("その1") + f1
    d1["not_fields"] = [{"label": "点検種別（機器点検）", "reason": "消火器具は機器点検のみ。実帳票では印字済み。固定文字として扱う（原本で要確認）"}]
    d1["rules"] = r1
    d1["equipment"] = "消火器具"
    out["KOKUJI-01-1.v0.1.json"] = d1

    f2, r2 = item_rows(SONO2_ITEMS)
    meters = []
    for i in range(1, 4):
        for side in ("L", "R"):
            for col, lab in (("name", "機器名"), ("model", "型式"), ("calib", "校正年月日"), ("maker", "製造者名")):
                meters.append(U(id=f"meter{i}{side}_{col}", label=f"測定機器 {i}行目{'左' if side == 'L' else '右'} {lab}",
                                input_type="日付" if col == "calib" else "文字", layer="L2",
                                source="自社の測定機器台帳", note="行数（3行×左右）は仮。原本で実測する"))
    d2 = base("KOKUJI-01-2", "消火器具点検票（その２）", "平成14年消防庁告示第14号 別記様式第1（その2）", "設備様式")
    d2["$comment"] = "消火器具点検票（その２）の帳票定義 初版。座標は全欄『未確定』で、生成器はフィールドを作らない。"
    d2["fixed_text_vocabulary"] = ["別記様式第１", "消火器具（その２）", "消火器の内部等・機能", "本体容器・内筒等", "消火薬剤",
                                   "簡易消火用具", "備考", "測定機器", "機器名", "型式", "校正年月日", "製造者名"] + [l for _, l in SONO2_ITEMS] + NOTES_COMMON
    d2["fields"] = f2 + [
        U(id="remarks", label="備考", input_type="文字", layer="L3", capacity={"max_lines": None, "max_chars_per_line": None},
          note="実帳票では、未確認の理由（例：客先都合により未確認）や器種別の集計（設置数・点検数・合格数・要修理数・廃棄数）が"
               "ここに書かれている。集計は点検結果から自動で作れる（手入力にしない）候補。容量は原本で実測する")] + meters
    d2["rules"] = r2
    d2["equipment"] = "消火器具"
    d2["open_questions"] = ["その2 に頭の部分（名称・点検年月日など）があるか", "備考欄の器種別集計を自動生成にするか（議題に出す）"]
    out["KOKUJI-01-2.v0.1.json"] = d2

    rows, rules = [], []
    n = 10  # 1シートの行数は仮。原本で実測する
    for i in range(1, n + 1):
        p = f"r{i}_"
        rows += [
            U(id=p + "no", label=f"{i}行目 番号", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "place", label=f"{i}行目 設置場所", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "kind", label=f"{i}行目 種別", input_type="固定・自動", layer="L2", source="消火器台帳", note="例：粉末(蓄圧)"),
            U(id=p + "model_no", label=f"{i}行目 型式番号", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "capacity", label=f"{i}行目 容量", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "maker", label=f"{i}行目 メーカー", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "made", label=f"{i}行目 製造年月", input_type="固定・自動", layer="L2", source="消火器台帳",
              note="実帳票では年のみの記入例あり。書式は原本で確認"),
            U(id=p + "serial", label=f"{i}行目 製造番号", input_type="固定・自動", layer="L2", source="消火器台帳"),
            U(id=p + "func_date", label=f"{i}行目 機能 年月日", input_type="日付", layer="L3",
              note="内部・機能点検の実施日とみられる。L2（前回値の引き継ぎ）か L3 か要確認"),
            U(id=p + "judge", label=f"{i}行目 判定", input_type="記号", layer="L3", judgment=True, allowed=["○", "×"],
              note="様式の注記：良好＝○、不良＝×"),
            U(id=p + "note", label=f"{i}行目 備考", input_type="文字", layer="L3", capacity={"max_lines": 1}),
        ]
        rules.append({"id": f"r{i}-defect-note", "kind": "required_if", "if": {"field": p + "judge", "in": ["×"]},
                      "then": p + "note", "reason": "× のため備考（不良の内容）が必須"})
        rules.append({"id": f"r{i}-unconfirmed", "kind": "unconfirmed_if", "field": p + "judge", "marker_field": p + "note",
                      "contains": "未確認", "reason": "備考に「未確認」があるため、判定は空欄のまま「未確認」として数える（合格に含めない）",
                      "conflict_reason": "備考に「未確認」があるのに判定が入っている"})
    d3 = base("SHOKAKI-KANRI", "消火器管理票", "法定様式ではない（点検票の別紙。業界・社内の様式）", "台帳系（設備様式の別紙）")
    d3["$comment"] = "消火器管理票（別紙）の帳票定義 初版。台帳系：様式を変えずシートの枚数が増え、右上に（i/n）を付ける。座標は全欄『未確定』。"
    d3["fixed_text_vocabulary"] = ["別紙", "消火器管理票", "名称", "番号", "設置場所", "種別", "型式番号", "容量", "メーカー", "製造年月",
                                   "製造番号", "機能", "年月日", "判定", "備考", "注）判定欄の記入方法", "良好な場合･･･○", "不良な場合･･･×"]
    d3["fields"] = [U(id="site_name", label="名称", input_type="文字", layer="L2", capacity={"max_lines": 1}, source="物件台帳")] + rows
    d3["repeat"] = {"rows_per_sheet": None, "rows_defined": n, "note": "1シートの行数は原本で実測する。物件の消火器の総数からシート数 n を決める"}
    d3["sheet_counter"] = {"coord_status": "未確定", "x_right": None, "y": None, "size": None, "format": "（{i}/{n}）",
                           "note": "事業側 2026-11-11：各シート右上に（i/n）。原本に枚数欄が既にあるかは実測で確認"}
    d3["rules"] = rules
    d3["equipment"] = "消火器具"
    out["SHOKAKI-KANRI.v0.1.json"] = d3

    for name, d in out.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        print(name, "fields", len(d["fields"]), "rules", len(d.get("rules", [])))


if __name__ == "__main__":
    build()
