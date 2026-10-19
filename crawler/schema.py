"""
NISA比較サイトが扱う投資信託1本分のデータ構造の定義。

この形は site/data.js の `const FUNDS = [...]` の中身と1対1で対応している。
クローリングで取得した情報は、最終的にすべてこの形に変換してから
data/funds.json に保存する。
"""

from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple


@dataclass
class Fund:
    isin_cd: str                       # ISINコード（一意なキーとして使う）
    name: str                          # 商品名
    company: str                       # 運用会社名
    standard_price: Optional[float]    # 基準価額（円、1万口あたり）
    trust_reward_pct: Optional[float]  # 信託報酬率（％、税込・年率）
    total_net_assets_myen: Optional[float]  # 純資産総額（百万円）
    return_1y_pct: Optional[float]     # 1年リターン（％）。最新基準日で毎日計算（returns.py）。計算できない場合は公表値（前月末基準）
    return_3y_pct: Optional[float]     # 騰落率（3年、％）。最新基準日で毎日計算（returns.py）。計算できない場合は公表値（前月末基準）
    dividend_yield_pct: Optional[float]  # 分配金利回り（％）＝ 直近1年分配金合計 ÷ 基準価額
    nisa_tsumitate: bool               # つみたて投資枠 対象か
    nisa_growth: bool                  # 成長投資枠 対象か
    prospectus_url: str                # 交付目論見書（PDF）へのリンク
    company_url: str                   # 運用会社サイトへのリンク（目論見書のドメインから推定）
    standard_date: str                 # このデータの基準日 (YYYY-MM-DD)
    source_checked_at: str = ""        # クローラーが取得した日付 (YYYY-MM-DD)
    price_history_1y: List[Tuple[str, float]] = field(default_factory=list)  # 直近1年の基準価額推移（間引き済み）
    return_1y_basis: str = "monthEnd"  # "daily"=最新基準日で計算（分配金再投資ベース） / "monthEnd"=投信協会の公表値（前月末基準）
    return_1y_from: str = ""           # 1年リターンの比較の起点日（daily のとき）
    return_1y_to: str = ""             # 1年リターンの計算に使った最新日（daily のとき）
    return_3y_basis: str = "monthEnd"  # 3年騰落率の基準（return_1y_basis と同じ意味）
    return_3y_from: str = ""
    return_3y_to: str = ""
    # 以下2つは価格推移チャートを取得するためだけに使う内部値。to_dict()では出力しない。
    associ_fund_cd: str = ""
    separate_div: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # JS側のキー名（キャメルケース）に変換
        return {
            "isinCd": d["isin_cd"],
            "name": d["name"],
            "company": d["company"],
            "standardPrice": d["standard_price"],
            "trustRewardPct": d["trust_reward_pct"],
            "totalNetAssetsMyen": d["total_net_assets_myen"],
            "return1yPct": d["return_1y_pct"],
            "return1yBasis": d["return_1y_basis"],
            "return1yFrom": d["return_1y_from"],
            "return1yTo": d["return_1y_to"],
            "return3yPct": d["return_3y_pct"],
            "return3yBasis": d["return_3y_basis"],
            "return3yFrom": d["return_3y_from"],
            "return3yTo": d["return_3y_to"],
            "dividendYieldPct": d["dividend_yield_pct"],
            "nisaTsumitate": d["nisa_tsumitate"],
            "nisaGrowth": d["nisa_growth"],
            "prospectusUrl": d["prospectus_url"],
            "companyUrl": d["company_url"],
            "standardDate": d["standard_date"],
            "sourceCheckedAt": d["source_checked_at"],
            "priceHistory1y": d["price_history_1y"],
        }
