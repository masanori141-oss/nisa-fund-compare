"""
投資信託協会（資産運用業協会）が運営する「投信総合検索ライブラリー」
(https://toushin-lib.fwg.ne.jp/FdsWeb/FDST999900) から、NISA対象
（つみたて投資枠 または 成長投資枠）の投資信託データを取得する。

【重要な注意】
ここで叩いているエンドポイント（/FdsWeb/FDST999900/fundDataSearch）は、
検索ページ自身がJavaScriptから内部的に呼び出しているAJAX用のAPIであり、
公式に「外部利用可能」とドキュメント化されたAPIではない（robots.txtでの
明示的な禁止は確認できなかったが、いつ仕様変更されてもおかしくない）。
そのため、
  - 1日1回程度の穏やかな頻度でのみ呼び出す
  - リクエスト間に間隔を空ける（REQUEST_DELAY_SEC）
  - 分かりやすい User-Agent を送る
という配慮をした上で利用している。もし仕様変更で取得できなくなった場合は、
このファイルのペイロード（PAYLOAD_TEMPLATE）やフィールド名を、実際の
ページのJavaScript（/static/js/web/FDST9999/FDST999900.js,
FDST999999.js）を見ながら調整する必要がある。
"""

import time
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from .schema import Fund

SEARCH_URL = "https://toushin-lib.fwg.ne.jp/FdsWeb/FDST999900/fundDataSearch"
REFERER_URL = "https://toushin-lib.fwg.ne.jp/FdsWeb/FDST999900"
CHART_URL = "https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000/get-basis-price-chart-date"
CHART_REFERER_TMPL = "https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000?isinCd={isin_cd}"
PAGE_SIZE = 20  # サーバー側で固定（リクエストパラメータでは変更できない）
REQUEST_DELAY_SEC = 0.4
CHART_REQUEST_DELAY_SEC = 0.35
CHART_TERM_FLG_1Y = 12  # 「1年」ボタンに相当する値
CHART_MAX_POINTS = 52   # 週次相当まで間引く（サイト・リポジトリへの負荷を抑えるため）
MAX_RETRIES = 3
USER_AGENT = (
    "nisa-fund-compare-crawler/1.0 "
    "(personal project; daily update for a NISA fund comparison site)"
)

# サーバー側が配列として扱うことを期待しているフィールド。
# 空リストのままにしておけば「絞り込みなし」を意味する。
ARRAY_FIELDS = [
    "s_investAssetKindCd", "s_investArea3kindCd", "s_instCd", "s_fdsInstCd",
    "s_dcFundCD", "t_investArea10kindCd", "t_investAssetKindCd", "t_instCd",
    "t_fdsInstCd", "s_investArea10kindCd", "s_setlFqcy", "s_dividend1y",
    "s_totalNetAssets", "s_nowToRedemptionDate", "s_establishedDateToNow",
    "s_isinCd",
]

# s_nisaGrowthCd = "2" は「つみたて投資枠または成長投資枠」（=NISA対象の和集合）
NISA_UNION_CODE = "2"


def _build_payload(start_no: int) -> dict:
    payload = {field: [] for field in ARRAY_FIELDS}
    payload.update({
        "s_nisaGrowthCd": NISA_UNION_CODE,
        "startNo": start_no,
        "draw": 1,
        "searchBtnClickFlg": True,
    })
    return payload


def _company_url_from_prospectus(prospectus_url: Optional[str]) -> str:
    """目論見書PDFのドメインから、運用会社サイトのトップページURLを推定する。"""
    if not prospectus_url:
        return ""
    try:
        parts = urlsplit(prospectus_url)
        if not parts.scheme or not parts.netloc:
            return ""
        return f"{parts.scheme}://{parts.netloc}/"
    except ValueError:
        return ""


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_record(rec: dict, standard_date: str, today: str) -> Optional[Fund]:
    isin_cd = rec.get("isinCd")
    name = rec.get("fundStNm") or rec.get("fundNm")
    if not isin_cd or not name:
        return None

    standard_price = _to_float(rec.get("standardPrice"))
    dividend_1y = _to_float(rec.get("dividend1y"))
    dividend_yield_pct = None
    if standard_price and dividend_1y is not None and standard_price > 0:
        dividend_yield_pct = round(dividend_1y / standard_price * 100, 3)

    prospectus_url = rec.get("reportUrl") or ""

    return Fund(
        isin_cd=isin_cd,
        name=name.strip(),
        company=(rec.get("entrustCmpNm") or "").strip(),
        standard_price=standard_price,
        trust_reward_pct=_to_float(rec.get("trustReward")),
        total_net_assets_myen=_to_float(rec.get("totalNetAssets")),
        return_1y_pct=_to_float(rec.get("standardPriceRa1y")),
        return_3y_pct=_to_float(rec.get("standardPriceRa3y")),
        dividend_yield_pct=dividend_yield_pct,
        nisa_tsumitate=str(rec.get("nisaFlg")) == "1",
        nisa_growth=str(rec.get("nisaGrowthFlg")) == "1",
        prospectus_url=prospectus_url,
        company_url=_company_url_from_prospectus(prospectus_url),
        standard_date=standard_date,
        source_checked_at=today,
        associ_fund_cd=rec.get("associFundCd") or "",
        separate_div=str(rec.get("separateseparateDiv") or "0"),
    )


def _resample(points: List[Tuple[str, float]], max_points: int) -> List[Tuple[str, float]]:
    """先頭・末尾を保ったまま、点数が多すぎる場合は間引く。"""
    if len(points) <= max_points:
        return points
    n = len(points)
    idx = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return [points[i] for i in idx]


def _fetch_price_history(session: requests.Session, fund: Fund) -> List[Tuple[str, float]]:
    if not fund.associ_fund_cd:
        return []
    payload = {
        "termFlg": CHART_TERM_FLG_1Y,
        "associFundCd": fund.associ_fund_cd,
        "separateseparateDiv": fund.separate_div,
    }
    headers = {
        "Referer": CHART_REFERER_TMPL.format(isin_cd=fund.isin_cd),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = session.post(CHART_URL, data=payload, headers=headers, timeout=30)
            res.raise_for_status()
            data = res.json()
            raw = data.get("basisPriceData") or []
            points = []
            for item in raw:
                if not item or len(item) < 2 or item[1] in (None, ""):
                    continue
                date_part = str(item[0]).split(" ")[0].replace("/", "-")
                try:
                    price = round(float(item[1]), 1)
                except (TypeError, ValueError):
                    continue
                points.append((date_part, price))
            return _resample(points, CHART_MAX_POINTS)
        except (requests.RequestException, ValueError) as e:
            last_error = e
            time.sleep(CHART_REQUEST_DELAY_SEC * attempt)
    print(f"    [警告] 価格推移の取得に失敗（{fund.isin_cd}）: {last_error}")
    return []


def _post_with_retry(session: requests.Session, payload: dict) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = session.post(SEARCH_URL, json=payload, timeout=30)
            res.raise_for_status()
            return res.json()
        except (requests.RequestException, ValueError) as e:
            last_error = e
            print(f"    [警告] リクエスト失敗（{attempt}/{MAX_RETRIES}回目）: {e}")
            time.sleep(REQUEST_DELAY_SEC * attempt)
    raise RuntimeError(f"投信総合検索ライブラリーへのリクエストが{MAX_RETRIES}回とも失敗しました: {last_error}")


def fetch_nisa_funds() -> List[Fund]:
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": REFERER_URL,
        "User-Agent": USER_AGENT,
    })

    today = datetime.now().strftime("%Y-%m-%d")
    funds: List[Fund] = []
    seen_isin = set()

    first = _post_with_retry(session, _build_payload(0))
    info = first.get("searchResultInfo", {})
    total = int(info.get("recordsTotal", 0))
    standard_date_raw = info.get("standardDate") or ""
    standard_date = standard_date_raw.split(" ")[0] if standard_date_raw else today

    print(f"    対象件数: {total} 件（基準日: {standard_date}）")

    def consume_page(payload_info: dict):
        for rec in payload_info.get("resultInfoMapList", []):
            fund = _parse_record(rec, standard_date, today)
            if fund and fund.isin_cd not in seen_isin:
                seen_isin.add(fund.isin_cd)
                funds.append(fund)

    consume_page(info)

    start_no = PAGE_SIZE
    while start_no < total:
        time.sleep(REQUEST_DELAY_SEC)
        page = _post_with_retry(session, _build_payload(start_no))
        page_info = page.get("searchResultInfo", {})
        consume_page(page_info)
        if (start_no // PAGE_SIZE) % 10 == 0:
            print(f"    取得中... {len(funds)}/{total} 件")
        start_no += PAGE_SIZE

    print(f"    取得完了: {len(funds)} 件")

    print("    基準価額の1年推移（チャート用データ）を取得中...")
    for i, fund in enumerate(funds, start=1):
        fund.price_history_1y = _fetch_price_history(session, fund)
        if i % 200 == 0:
            print(f"    チャート取得中... {i}/{len(funds)} 件")
        time.sleep(CHART_REQUEST_DELAY_SEC)
    print("    チャート用データの取得完了")

    return funds


if __name__ == "__main__":
    result = fetch_nisa_funds()
    for f in result[:5]:
        print(f.name, "|", f.company, "|", f.trust_reward_pct, "|", f.total_net_assets_myen)
