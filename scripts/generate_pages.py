"""
data/funds.json から、検索エンジン対策（SEO）用の静的HTMLを生成する。

    python scripts/generate_pages.py

生成されるもの:
  - site/funds/<ISINコード>.html   … ファンド1本ごとの詳細ページ
                                     （基準価額の1年推移チャートを含む。
                                       JavaScriptなしでも内容が読める）
  - site/list/page-N.html          … 一覧の静的ページ（100件ずつ）
                                     （index.htmlの絞り込みUIとは別に、
                                       検索エンジンや非JS環境向けに
                                       全件をHTMLソースとして持たせる）
  - site/index.html                … templates/index.html を元に、
                                       先頭50件分のファンド行をHTML
                                       ソースへ直接埋め込んだもの
                                       （JavaScriptなしでもトップページに
                                       投信情報が載るようにするため。
                                       JS実行後は同じ内容がそのまま
                                       絞り込み・並び替え結果で上書きされる）
  - site/sitemap.xml               … 上記すべてのURLを列挙したサイトマップ
  - site/robots.txt                … クロール許可設定

【重要】site/index.html は自動生成物です。直接編集しないでください。
編集する場合は templates/index.html を直してから、このスクリプトを
再実行してください。
"""

import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "funds.json"
SITE_DIR = ROOT / "site"
FUNDS_DIR = SITE_DIR / "funds"
LIST_DIR = SITE_DIR / "list"
TEMPLATE_PATH = ROOT / "templates" / "index.html"
SSR_ROW_COUNT = 50  # index.htmlのJS側の初期ページサイズ(PAGE_SIZE)と合わせる

# GitHub Pagesで公開する想定のURL。リポジトリ名やユーザー名を変えた場合はここも直すこと。
SITE_BASE_URL = "https://masanori141-oss.github.io/nisa-fund-compare/"

LIST_PAGE_SIZE = 100


def sort_key(fund):
    """1年リターンが高い順→（同水準なら）信託報酬率が高い順。"""
    r1 = fund.get("return1yPct")
    reward = fund.get("trustRewardPct")
    r1_sort = r1 if r1 is not None else float("-inf")
    reward_sort = reward if reward is not None else float("-inf")
    return (-r1_sort, -reward_sort)


def fmt_price(v):
    return f"{v:,.0f}円" if v is not None else "—"


def fmt_pct(v, digits=2):
    if v is None:
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{digits}f}%"


def fmt_assets_oku(myen):
    if myen is None:
        return "—"
    return f"{myen / 100:,.0f}億円"


def esc(s):
    return html.escape(str(s), quote=True)


def nisa_badges(fund):
    badges = []
    if fund.get("nisaTsumitate"):
        badges.append('<span class="badge tsumitate">つみたて投資枠</span>')
    if fund.get("nisaGrowth"):
        badges.append('<span class="badge growth">成長投資枠</span>')
    return "".join(badges)


def svg_price_chart(history):
    if not history or len(history) < 2:
        return '<p class="chart-empty">この投資信託については、直近1年の基準価額推移データがまだありません。</p>'

    prices = [p for _, p in history]
    w, h = 640, 240
    pad_l, pad_r, pad_t, pad_b = 56, 12, 20, 30
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min:
        p_max = p_min + 1
    n = len(prices)

    def x_at(i):
        return pad_l + (plot_w * i / (n - 1))

    def y_at(p):
        return pad_t + plot_h - (plot_h * (p - p_min) / (p_max - p_min))

    line_pts = " ".join(f"{x_at(i):.1f},{y_at(p):.1f}" for i, p in enumerate(prices))
    area_pts = f"{x_at(0):.1f},{pad_t + plot_h:.1f} " + line_pts + f" {x_at(n - 1):.1f},{pad_t + plot_h:.1f}"

    change_pct = (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else 0
    color = "#1E6B41" if change_pct >= 0 else "#B93C28"
    fill = "#EAF2EC" if change_pct >= 0 else "#F7EAE7"

    start_date, start_price = history[0]
    end_date, end_price = history[-1]

    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img"
  aria-label="基準価額の1年推移チャート。{esc(start_date)}に{start_price:,.0f}円、{esc(end_date)}に{end_price:,.0f}円（{fmt_pct(change_pct)}）。">
  <title>基準価額の1年推移（{esc(start_date)}〜{esc(end_date)}）</title>
  <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" stroke="#DEDCD4" stroke-width="1"/>
  <line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{w - pad_r}" y2="{pad_t + plot_h}" stroke="#DEDCD4" stroke-width="1"/>
  <text x="{pad_l - 6}" y="{pad_t + 4}" font-size="11" fill="#5B5D5F" text-anchor="end">{p_max:,.0f}円</text>
  <text x="{pad_l - 6}" y="{pad_t + plot_h + 4}" font-size="11" fill="#5B5D5F" text-anchor="end">{p_min:,.0f}円</text>
  <polygon points="{area_pts}" fill="{fill}" stroke="none"/>
  <polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{x_at(n - 1):.1f}" cy="{y_at(prices[-1]):.1f}" r="3" fill="{color}"/>
  <text x="{pad_l}" y="{h - 8}" font-size="11" fill="#5B5D5F" text-anchor="start">{esc(start_date)}（{start_price:,.0f}円）</text>
  <text x="{w - pad_r}" y="{h - 8}" font-size="11" fill="#5B5D5F" text-anchor="end">{esc(end_date)}（{end_price:,.0f}円）</text>
</svg>
<p class="chart-caption">この1年間の騰落率：<strong class="{'pos' if change_pct >= 0 else 'neg'}">{fmt_pct(change_pct)}</strong>
（{esc(start_date)} の {start_price:,.0f}円 → {esc(end_date)} の {end_price:,.0f}円。投信総合検索ライブラリーの公開データをもとに、約1週間おきの値を抜き出して作成しています。）</p>'''


PAGE_HEAD = '''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-MVQZEB89RS"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());

  gtag('config', 'G-MVQZEB89RS');
</script>
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<link href="{asset_prefix}style.css" rel="stylesheet">
</head>
<body>
<div class="topbar"><div class="topbar-inner">
  <a class="brand" href="{root_prefix}index.html"><span class="mark">信</span>NISA投信比較</a>
  <nav class="topnav"><a href="{root_prefix}index.html">絞り込み検索</a><a href="{root_prefix}list/page-1.html">一覧をすべて見る</a></nav>
</div></div>
'''

PAGE_FOOT = '''
<footer>NISA投信比較 — データ提供：投資信託協会「投信総合検索ライブラリー」／毎日自動更新</footer>
</body>
</html>
'''


def render_fund_page(fund):
    name = esc(fund["name"])
    company = esc(fund["company"])
    isin = fund["isinCd"]
    description = (
        f"{fund['name']}（{fund['company']}）の基準価額 {fmt_price(fund.get('standardPrice'))}・"
        f"信託報酬率 {fund.get('trustRewardPct')}%・純資産総額 {fmt_assets_oku(fund.get('totalNetAssetsMyen'))}。"
        f"1年リターン {fmt_pct(fund.get('return1yPct'))}、直近1年の基準価額推移チャート付き。"
    )
    company_cell = f'<a href="{esc(fund["companyUrl"])}" target="_blank" rel="noopener">{company}</a>' if fund.get("companyUrl") else company
    prospectus_cell = (
        f'<a href="{esc(fund["prospectusUrl"])}" target="_blank" rel="noopener">交付目論見書（PDF）を見る →</a>'
        if fund.get("prospectusUrl") else "<span class=\"muted\">この投資信託については目論見書PDFの掲載がありません</span>"
    )

    head = PAGE_HEAD.format(
        title=esc(f"{fund['name']}｜基準価額・信託報酬率・チャート | NISA投信比較"),
        description=esc(description),
        asset_prefix="../",
        root_prefix="../",
    )

    body = f'''
<main class="fund-detail">
  <p class="breadcrumb"><a href="../list/page-1.html">一覧</a> ›  ファンド詳細</p>
  <h1 class="fund-detail-title">{name}</h1>
  <div class="badges-row">{nisa_badges(fund)}</div>
  <div class="stat-list">
    <div class="stat-row"><span class="stat-label">運用会社</span><span class="stat-value">{company_cell}</span></div>
    <div class="stat-row"><span class="stat-label">基準価額</span><span class="stat-value num">{fmt_price(fund.get("standardPrice"))}</span></div>
    <div class="stat-row"><span class="stat-label">信託報酬率</span><span class="stat-value num">{fund.get("trustRewardPct")}%</span></div>
    <div class="stat-row"><span class="stat-label">純資産総額</span><span class="stat-value num">{fmt_assets_oku(fund.get("totalNetAssetsMyen"))}</span></div>
    <div class="stat-row"><span class="stat-label">1年リターン（騰落率）</span><span class="stat-value num">{fmt_pct(fund.get("return1yPct"))}</span></div>
    <div class="stat-row"><span class="stat-label">騰落率（3年）</span><span class="stat-value num">{fmt_pct(fund.get("return3yPct"))}</span></div>
    <div class="stat-row"><span class="stat-label">目論見書</span><span class="stat-value">{prospectus_cell}</span></div>
  </div>

  <h2 class="section-h2">基準価額の推移（過去1年）</h2>
  <div class="chart-box">{svg_price_chart(fund.get("priceHistory1y") or [])}</div>

  <div class="broker-box">
    <div class="broker-box-label">実際にこの投資信託を購入するには</div>
    <p class="broker-box-note">多くの投資信託は、運用会社から直接購入できる場合もありますが、一般的にはネット証券などで証券総合口座・NISA口座を開設して購入します。以下は主要ネット証券の公式サイトです（口座開設状況・取扱商品は各社サイトでご確認ください）。</p>
    <div class="broker-links">
      <a href="https://www.sbisec.co.jp/" target="_blank" rel="noopener">SBI証券</a>
      <a href="https://www.rakuten-sec.co.jp/" target="_blank" rel="noopener">楽天証券</a>
      <a href="https://www.monex.co.jp/" target="_blank" rel="noopener">マネックス証券</a>
      <a href="https://www.matsui.co.jp/" target="_blank" rel="noopener">松井証券</a>
      <a href="https://kabu.com/" target="_blank" rel="noopener">三菱UFJ eスマート証券</a>
      <a href="https://www.paypay-sec.co.jp/" target="_blank" rel="noopener">PayPay証券</a>
    </div>
  </div>

  <p class="fund-detail-note">
    基準日：{esc(fund.get("standardDate", ""))}／データ取得日：{esc(fund.get("sourceCheckedAt", ""))}<br>
    データ提供：投資信託協会「投信総合検索ライブラリー」。投資判断の際は、必ず目論見書・運用報告書など公式資料をご確認ください。
    本ページの情報の正確性・最新性について保証するものではありません。
  </p>
  <p><a href="../list/page-1.html">← 一覧に戻る</a> ｜ <a href="../index.html">条件を絞り込んで探す →</a></p>
</main>
'''
    return head + body + PAGE_FOOT


def render_list_page(funds_page, page_num, total_pages):
    rows = []
    for f in funds_page:
        rows.append(f'''<tr>
      <td><a href="../funds/{esc(f["isinCd"])}.html">{esc(f["name"])}</a><br>{nisa_badges(f)}
      <div class="fund-chart-link"><a href="../funds/{esc(f["isinCd"])}.html">チャートを見る →</a></div></td>
      <td class="num">{f.get("trustRewardPct")}%</td>
      <td class="num">{fmt_pct(f.get("return1yPct"))}</td>
      <td class="num">{fmt_pct(f.get("return3yPct"))}</td>
    </tr>''')

    pager = []
    if page_num > 1:
        pager.append(f'<a href="page-{page_num - 1}.html">‹ 前の100件</a>')
    pager.append(f'<span class="page-info">{page_num} / {total_pages} ページ</span>')
    if page_num < total_pages:
        pager.append(f'<a href="page-{page_num + 1}.html">次の100件 ›</a>')

    head = PAGE_HEAD.format(
        title=esc(f"NISA対象 投資信託一覧（{page_num}/{total_pages}ページ目・1年リターンの高い順）| NISA投信比較"),
        description=esc(f"NISA制度のつみたて投資枠・成長投資枠対象の投資信託を、1年リターンの高い順に掲載（{page_num}/{total_pages}ページ目）。信託報酬率・騰落率も掲載。基準価額・純資産総額・目論見書は各ファンドの詳細ページに掲載。"),
        asset_prefix="../",
        root_prefix="../",
    )
    body = f'''
<main class="list-page">
  <h1 class="list-title">NISA対象 投資信託一覧（1年リターンの高い順）</h1>
  <p class="list-lede">つみたて投資枠・成長投資枠の対象となっている投資信託を、1年リターンが高い順（同水準の場合は信託報酬率が高い順）に並べています。より細かい条件で絞り込みたい場合は<a href="../index.html">絞り込み検索ページ</a>をご利用ください。NISA制度の仕組みや税制メリットについては<a href="../index.html#nisa-guide">NISAまるわかりガイド</a>をご覧ください。</p>
  <div class="pager top">{" ".join(pager)}</div>
  <div class="table-scroll">
  <table>
    <thead><tr>
      <th>商品名</th><th>信託報酬率</th><th>1年リターン</th><th>騰落率(3年)</th>
    </tr></thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
  </div>
  <div class="pager bottom">{" ".join(pager)}</div>
</main>
'''
    return head + body + PAGE_FOOT


SITE_CSS = '''
:root{--bg:#FFFFFF;--bg-soft:#F6F7F5;--line:#DEDCD4;--line-strong:#C7C4B8;--navy:#173250;--navy-deep:#0E1F33;--vermillion:#B93C28;--green:#1E6B41;--gold:#8A6A22;--text:#1C1E22;--text-sub:#5B5D5F;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);font-family:'Zen Kaku Gothic New','Hiragino Sans',sans-serif;-webkit-font-smoothing:antialiased;}
a{color:var(--navy);}
.topbar{background:#fff;border-bottom:1px solid var(--line);padding:14px 24px;}
.topbar-inner{max-width:1100px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.brand{font-weight:800;font-size:18px;display:flex;align-items:center;gap:8px;color:var(--navy-deep);text-decoration:none;}
.brand .mark{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border:1.5px solid var(--vermillion);color:var(--vermillion);border-radius:50%;font-size:11px;font-weight:700;}
.topnav a{font-size:13px;font-weight:600;text-decoration:none;color:var(--text-sub);margin-left:18px;}
.topnav a:hover{color:var(--navy);}
main{max-width:1100px;margin:0 auto;padding:24px 24px 60px;}
.breadcrumb{font-size:12px;color:var(--text-sub);}
.fund-detail-title{font-size:22px;font-weight:800;color:var(--navy-deep);margin:6px 0 10px;}
.badges-row{margin-bottom:16px;}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;margin-right:6px;}
.badge.tsumitate{background:#EAF2EC;color:var(--green);}
.badge.growth{background:#EAF0F5;color:var(--navy);}
.fund-chart-link{margin-top:4px;}
.fund-chart-link a{font-size:11.5px;color:var(--navy);text-decoration:none;border-bottom:1px solid var(--line-strong);white-space:nowrap;}
.fund-chart-link a:hover{color:var(--vermillion);border-color:var(--vermillion);}
.stat-list{max-width:560px;margin-bottom:26px;font-size:14px;}
.stat-row{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);}
.stat-label{flex:0 0 38%;max-width:38%;color:var(--text-sub);font-weight:600;}
.stat-value{flex:1 1 auto;min-width:0;overflow-wrap:anywhere;word-break:break-word;}
.stat-value.num{font-variant-numeric:tabular-nums;}
.section-h2{font-size:16px;font-weight:800;color:var(--navy-deep);margin:28px 0 12px;}
.chart-box{border:1px solid var(--line);border-radius:4px;padding:16px;background:#fff;max-width:680px;}
.chart-box svg{width:100%;height:auto;}
.chart-caption{font-size:12px;color:var(--text-sub);margin:10px 0 0;line-height:1.7;}
.chart-caption .pos{color:var(--green);font-weight:700;}
.chart-caption .neg{color:var(--vermillion);font-weight:700;}
.broker-box{margin-top:20px;max-width:680px;padding:16px 20px;background:#FBF6EC;border:1px solid #E7D9B2;border-radius:4px;}
.broker-box-label{font-size:12.5px;font-weight:700;color:var(--gold);letter-spacing:.02em;margin-bottom:6px;}
.broker-box-note{font-size:12px;color:var(--text-sub);line-height:1.8;margin:0 0 12px;}
.broker-links{display:flex;flex-wrap:wrap;gap:8px;}
.broker-links a{font-size:13px;font-weight:700;color:var(--navy-deep);background:#fff;border:1px solid #E7D9B2;padding:8px 16px;border-radius:999px;text-decoration:none;}
.broker-links a:hover{border-color:var(--gold);color:var(--gold);}
.fund-detail-note{font-size:11.5px;color:var(--text-sub);line-height:1.8;margin-top:26px;border-top:1px solid var(--line);padding-top:14px;}
.list-title{font-size:20px;font-weight:800;color:var(--navy-deep);margin:6px 0 8px;}
.list-lede{font-size:13px;color:var(--text-sub);line-height:1.8;max-width:820px;margin:0 0 16px;}
.pager{display:flex;align-items:center;gap:14px;font-size:13px;margin:14px 0;flex-wrap:wrap;}
.pager.top{justify-content:flex-end;}
.pager.bottom{justify-content:center;}
.page-info{color:var(--text-sub);}
.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:4px;}
table{border-collapse:collapse;width:100%;min-width:480px;font-size:13px;}
thead th{background:var(--bg-soft);border-bottom:2px solid var(--line-strong);padding:9px 10px;text-align:right;font-size:11px;color:var(--text-sub);white-space:nowrap;}
thead th:first-child{text-align:left;}
tbody td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top;}
tbody td:first-child{text-align:left;}
tbody tr:hover{background:var(--bg-soft);}
.num{font-variant-numeric:tabular-nums;}
.muted{color:var(--text-sub);}
footer{background:var(--navy-deep);color:rgba(255,255,255,0.55);text-align:center;padding:20px 24px;font-size:11px;margin-top:20px;}

@media (max-width:600px){
  main{padding-left:16px;padding-right:16px;}
  .topbar{padding-left:16px;padding-right:16px;}
  .stat-list{font-size:13px;}
  .fund-detail-title{font-size:19px;}
}
'''


def fmt_pct_colored(v):
    """index.html側のJS（fmtPct関数）と同じ見た目になるよう、色分けした形で返す。"""
    if v is None:
        return '<span class="muted">—</span>'
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.2f}%</span>'


def render_index_ssr_row(f):
    """index.htmlのJS（render関数）が生成するのと同じ形の<tr>を、Python側で組み立てる。"""
    chart_link = (
        f'<div class="fund-chart-link"><a href="funds/{esc(f["isinCd"])}.html">'
        "チャートを見る →</a></div>"
    )
    reward = f.get("trustRewardPct")
    reward_html = f"{reward:.3f}" if reward is not None else '<span class="muted">—</span>'
    return f'''<tr>
      <td><div class="fund-name">{esc(f["name"])}</div>{nisa_badges(f)}{chart_link}</td>
      <td class="num">{reward_html}%</td>
      <td class="num">{fmt_pct_colored(f.get("return1yPct"))}</td>
      <td class="num">{fmt_pct_colored(f.get("return3yPct"))}</td>
    </tr>'''


def render_index_html(funds_sorted):
    """templates/index.html を元に、先頭SSR_ROW_COUNT件のファンド行を
    HTMLソースへ直接埋め込んだ site/index.html を生成する。

    これにより、JavaScriptを実行しないクローラー（一部の検索エンジンや
    AI検索エンジンのクローラーなど）でも、トップページの時点で実際の
    投信情報とファンド詳細ページへのリンクを読み取れるようにしている。
    JavaScriptが実行された場合は、絞り込み・並び替えの結果で同じ
    tbody の中身がそのまま上書きされる（表示内容は変わらない）。
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rows_html = "".join(render_index_ssr_row(f) for f in funds_sorted[:SSR_ROW_COUNT])
    if "<!--SSR_FUND_ROWS-->" not in template:
        raise RuntimeError(
            "templates/index.html に <!--SSR_FUND_ROWS--> のプレースホルダーが見つかりません。"
        )
    output = template.replace("<!--SSR_FUND_ROWS-->", rows_html)
    output = output.replace(
        "<!DOCTYPE html>",
        "<!DOCTYPE html>\n<!-- 自動生成ファイル。直接編集せず templates/index.html を編集してください。 -->",
        1,
    )
    (SITE_DIR / "index.html").write_text(output, encoding="utf-8")


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        funds = json.load(f)

    funds_sorted = sorted(funds, key=sort_key)

    FUNDS_DIR.mkdir(parents=True, exist_ok=True)
    LIST_DIR.mkdir(parents=True, exist_ok=True)

    with open(SITE_DIR / "style.css", "w", encoding="utf-8") as f:
        f.write(SITE_CSS)

    render_index_html(funds_sorted)

    for fund in funds_sorted:
        html_out = render_fund_page(fund)
        with open(FUNDS_DIR / f"{fund['isinCd']}.html", "w", encoding="utf-8") as f:
            f.write(html_out)

    total_pages = max(1, math.ceil(len(funds_sorted) / LIST_PAGE_SIZE))
    for page_num in range(1, total_pages + 1):
        start = (page_num - 1) * LIST_PAGE_SIZE
        chunk = funds_sorted[start:start + LIST_PAGE_SIZE]
        html_out = render_list_page(chunk, page_num, total_pages)
        with open(LIST_DIR / f"page-{page_num}.html", "w", encoding="utf-8") as f:
            f.write(html_out)

    urls = [SITE_BASE_URL, SITE_BASE_URL + "index.html"]
    urls += [f"{SITE_BASE_URL}list/page-{n}.html" for n in range(1, total_pages + 1)]
    urls += [f"{SITE_BASE_URL}funds/{fund['isinCd']}.html" for fund in funds_sorted]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sitemap.append(f"  <url><loc>{esc(u)}</loc></url>")
    sitemap.append("</urlset>")
    with open(SITE_DIR / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap) + "\n")

    with open(SITE_DIR / "robots.txt", "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}sitemap.xml\n")

    print(f"生成完了: index.html（SSR {min(SSR_ROW_COUNT, len(funds_sorted))}件）、ファンド詳細ページ {len(funds_sorted)} 件、一覧ページ {total_pages} 件、sitemap.xml、robots.txt")


if __name__ == "__main__":
    main()
