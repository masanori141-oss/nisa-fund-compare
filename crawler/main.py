"""
クローラー全体のエントリーポイント。

    python -m crawler.main

を実行すると、
  1. 投信総合検索ライブラリーからNISA対象（つみたて投資枠／成長投資枠）
     の投資信託データを取得
  2. 既存の data/funds.json とマージ
     （ISINコードをキーに上書き。今回取得できなかった銘柄は前回値を
     そのまま残す＝取得失敗で一覧がゼロ件になる事故を防ぐ）
  3. data/funds.json に書き戻す

という流れを1本で実行する。GitHub Actions からはこのスクリプトを
そのまま呼び出すだけでよい。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler.fetch_toushin_lib import fetch_nisa_funds

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "funds.json"


def load_existing() -> list:
    if DATA_PATH.exists():
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def merge(existing: list, fresh: list) -> list:
    by_isin = {item["isinCd"]: item for item in existing}
    for item in fresh:
        by_isin[item["isinCd"]] = item
    return list(by_isin.values())


def run():
    print(f"[{datetime.now().isoformat()}] クローリング開始")

    fresh_dicts = []
    try:
        funds = fetch_nisa_funds()
        fresh_dicts = [f.to_dict() for f in funds]
        print(f"  投信総合検索ライブラリー: {len(fresh_dicts)} 件")
    except Exception as e:
        print(f"  [警告] 投信総合検索ライブラリーの取得に失敗: {e}")

    existing = load_existing()
    merged = merge(existing, fresh_dicts)

    if not merged:
        print("  [エラー] 取得件数・既存データともに0件のため、保存を中止します。")
        sys.exit(1)

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[{datetime.now().isoformat()}] 完了。合計 {len(merged)} 件を保存しました。")


if __name__ == "__main__":
    run()
