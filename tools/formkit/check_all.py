"""全型の内容確認：各 form_id の最新版の定義を、匿名のダミーデータで1回ずつ生成して中身を確かめる。

見るもの（型ごと）：欄の数／作られた欄の数／入らなかった値（理由の種類別）／判定保留／ルール違反／
読み取り専用の欄の数／値のある欄のうち画面に表示されたものの数／完了可否（finalizable）。
結果は results/formkit-check/（summary.csv と report.md）。原本・記入値は使わない。

実行: python3 check_all.py
"""
from __future__ import annotations

import collections
import csv
import json
import os
import re

from pypdf import PdfReader

import formkit as fk
from selftest import REPO, field_ink, latest_definitions

OUT = os.path.join(REPO, "results", "formkit-check")
DATA = os.path.join(REPO, "forms", "data", "test")


def kind(issue: str) -> str:
    return re.split(r"[:：]", issue, maxsplit=1)[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    rows, details = [], {}
    for fid, path in latest_definitions().items():
        d = fk.load(path)
        dp = os.path.join(DATA, f"{fid}.dummy.json")
        data = fk.load(dp) if os.path.exists(dp) else {}
        data = {k: v for k, v in data.items() if not k.startswith("$")}
        pdf = os.path.join(OUT, f"{fid}.pdf")
        try:
            rep = fk.generate(d, data, pdf)
        except Exception as e:  # 例外も結果として残す（黙って飛ばさない）
            rows.append({"form_id": fid, "version": d.get("version"), "error": f"{type(e).__name__}: {e}"})
            continue
        fields = PdfReader(pdf).get_fields() or {}
        ro = sum(1 for v in fields.values() if int(v.get("/Ff", 0)) & 1)
        ink = field_ink(pdf, d)
        dropped = {x["id"] for x in rep["value_issues"]} | {x["id"] for x in rep["holds"]}
        with_value = [k for k, v in data.items() if v not in (None, "") and k in ink and k not in dropped]
        shown = [k for k in with_value if ink[k] > 0]  # 欄の内側（罫線から 2pt 内）に描画が少しでもあれば表示あり。大きな欄では割合が小さくなるため
        kinds = collections.Counter(kind(i) for x in rep["value_issues"] for i in x["issues"])
        rows.append({
            "form_id": fid, "version": d.get("version"), "fields": len(d["fields"]), "created": rep["fields_created"],
            "skipped": len(rep["fields_skipped"]), "data_values": sum(1 for v in data.values() if v not in (None, "")),
            "value_dropped": len(rep["value_issues"]), "drop_kinds": "; ".join(f"{k} {n}" for k, n in kinds.most_common()),
            "holds": len(rep["holds"]), "rule_issues": len(rep["rule_issues"]), "readonly": ro,
            "shown": f"{len(shown)}/{len(with_value)}", "finalizable": rep["finalizable"], "error": "",
        })
        details[fid] = {"value_issues": rep["value_issues"][:8], "not_shown": sorted(set(with_value) - set(shown))[:8],
                        "judgments": rep["judgments"]}
        os.remove(pdf)
    keys = ["form_id", "version", "fields", "created", "skipped", "data_values", "value_dropped", "drop_kinds",
            "holds", "rule_issues", "readonly", "shown", "finalizable", "error"]
    with open(os.path.join(OUT, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "details.json"), "w", encoding="utf-8") as fh:
        json.dump(details, fh, ensure_ascii=False, indent=1)
    for r in rows:
        print({k: r.get(k) for k in keys})


if __name__ == "__main__":
    main()
