"""
data/funds.json を、サイトが読み込む site/data.js に変換する。

    python scripts/export_to_data_js.py
"""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "funds.json"
OUT_PATH = ROOT / "site" / "data.js"


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        raw_funds = json.load(f)

    # 基準価額の1年推移（priceHistory1y）はファンド詳細ページ（generate_pages.py）
    # だけで使う。分配金利回り（dividendYieldPct）は絞り込み検索・一覧から
    # 削除したため、どちらも絞り込み検索ページ側では不要。含めると data.js が
    # 膨らんでしまうため、ここでは取り除く。
    drop_keys = {"priceHistory1y", "dividendYieldPct"}
    funds = [{k: v for k, v in f.items() if k not in drop_keys} for f in raw_funds]

    companies = sorted({f["company"] for f in funds if f.get("company")})
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append(f"// 自動生成ファイル。手で編集しないでください。")
    lines.append(f"// 生成日時: {generated_at}")
    lines.append(f"const GENERATED_AT = {json.dumps(generated_at, ensure_ascii=False)};")
    lines.append(f"const COMPANY_LIST = {json.dumps(companies, ensure_ascii=False)};")
    lines.append(f"const FUNDS = {json.dumps(funds, ensure_ascii=False)};")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"{OUT_PATH} を生成しました（{len(funds)}件、運用会社{len(companies)}社）。")


if __name__ == "__main__":
    main()
