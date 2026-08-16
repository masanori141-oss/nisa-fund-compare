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

    # 絞り込み検索ページ（index.html）が実際に使うフィールドだけを残す。
    # 基準価額・純資産総額・目論見書リンク・運用会社リンク・分配金利回り・
    # 価格推移などは一覧表示から削除済み（ファンド詳細ページでのみ使用）
    # なので、data.js には含めずスマホでの読み込みを軽くする。
    # company はキーワード検索（商品名・運用会社名）で使うため残す。
    keep_keys = {
        "isinCd", "name", "company", "trustRewardPct",
        "return1yPct", "return3yPct", "nisaTsumitate", "nisaGrowth",
    }
    funds = [{k: v for k, v in f.items() if k in keep_keys} for f in raw_funds]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append(f"// 自動生成ファイル。手で編集しないでください。")
    lines.append(f"// 生成日時: {generated_at}")
    lines.append(f"const GENERATED_AT = {json.dumps(generated_at, ensure_ascii=False)};")
    lines.append(f"const FUNDS = {json.dumps(funds, ensure_ascii=False)};")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"{OUT_PATH} を生成しました（{len(funds)}件）。")


if __name__ == "__main__":
    main()
