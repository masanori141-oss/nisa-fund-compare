"""
1年リターン・3年騰落率の計算。

投資信託協会「投信総合検索ライブラリー」の検索結果にある騰落率（standardPriceRa1y）は
**前月末を基準日とした値**で、月に1回しか変わらない。そのため、毎日更新している
基準価額のチャートと数値が食い違っていた（例：前月末基準 +165.31% と 最新 +114.31%）。

3年の騰落率（standardPriceRa3y）も同じく前月末基準のため、同じ方法で計算する。

ここでは、毎日取得している価格データから、最新の基準日時点の1年リターン・3年騰落率を計算する。
（1年は日次データ、3年は週次データ。3年の起点はチャートAPIの「3年」と同じく3年前の同日以降の最初の週）
  1年リターン ＝ 最新の価格 ÷ 1年前の価格 − 1
  - 価格は「分配金再投資基準価額」（分配金を受け取らずに再投資したとみなした価格）を使う。
    分配金を出すファンドでも、受け取った分配金を含めた実質的な成績になる
    （分配金を出さないファンドでは基準価額と同じ値）。
  - 1年前の価格：最新日の1年前の同日以前で最も新しい価格。
    データがその日より後から始まる場合は、7日以内のずれなら最初の価格を使う
    （週末・祝日で1年前の同日に価格が無い場合のため）。
    それより短い期間しかデータが無い（設定から1年未満など）場合は計算しない。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

Point = Tuple[str, float]  # ("YYYY-MM-DD", 価格)
MAX_START_GAP_DAYS = 7


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 2月29日
        return d.replace(year=d.year - years, day=28)


def one_year_before(d: date) -> date:
    return years_before(d, 1)


def compute_return_1y(points: Sequence[Point]) -> Optional[Tuple[float, str, str]]:
    """(1年リターン%, 比較の起点日, 最新日) を返す。計算できなければ None。"""
    return compute_return(points, 1)


def compute_return(points: Sequence[Point], years: int) -> Optional[Tuple[float, str, str]]:
    """(years年の騰落率%, 比較の起点日, 最新日) を返す。計算できなければ None。"""
    pts = sorted((p for p in points if p and p[1] and p[1] > 0), key=lambda p: p[0])
    if len(pts) < 2:
        return None
    end_date, end_price = pts[-1]
    target = years_before(_d(end_date), years)
    base: Optional[Point] = None
    for p in pts:
        if _d(p[0]) <= target:
            base = p
        else:
            break
    if base is None:
        first = pts[0]
        if (_d(first[0]) - target).days > MAX_START_GAP_DAYS:
            return None
        base = first
    pct = round((end_price / base[1] - 1) * 100, 2)
    return pct, base[0], end_date


def parse_series(raw: Optional[List[list]]) -> List[Point]:
    """チャートAPIの [["2026/10/16", "25177.0"], ...] を [("2026-10-16", 25177.0), ...] に変換。"""
    out: List[Point] = []
    for item in raw or []:
        if not item or len(item) < 2 or item[1] in (None, ""):
            continue
        try:
            out.append((str(item[0]).split(" ")[0].replace("/", "-"), round(float(item[1]), 1)))
        except (TypeError, ValueError):
            continue
    return out


def is_recent(as_of: str, today: str, max_days: int = 10) -> bool:
    """計算に使った最新日が、取得日から見て古すぎないか（チャートデータの更新停止を検知）。"""
    try:
        return (_d(today) - _d(as_of)) <= timedelta(days=max_days)
    except ValueError:
        return False
