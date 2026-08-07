"""ロール詳細ページの共通プレースホルダを生成する。"""

from site_builder.render import NAV_STYLES, esc, render_navigation


ROLE_PAGES = (
    ("support", "SUP", "support.html"),
    ("mid", "MID", "mid.html"),
    ("top", "TOP", "top.html"),
    ("adc", "ADC", "adc.html"),
    ("jungle", "JG", "jungle.html"),
)


ROLE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title} · LoL 実績</title>
<style>
  :root {{
    --bg: #0f1420; --panel: #171d2b; --panel2: #1e2635; --border: #2a3346;
    --text: #e7ecf4; --muted: #8a94a7; --accent: #5b8cff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
      "Noto Sans JP", Meiryo, sans-serif; line-height: 1.5;
  }}
  a {{ color: var(--accent); }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 24px 16px 64px; }}
  header.hero {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; margin-bottom: 24px;
  }}
  .hero h1 {{ margin: 0; font-size: 1.7rem; }}
  .role-placeholder {{
    border: 1px solid var(--border); border-radius: 12px; padding: 24px;
    background: var(--panel);
  }}
  .role-placeholder h2 {{ margin: 0 0 12px; }}
{navigation_styles}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero"><h1>{page_title}</h1></header>
    {navigation}
    <main class="role-placeholder">
      <h2>対象ロール: {role_name}</h2>
      <a href="index.html">TOPへ戻る</a>
    </main>
  </div>
</body>
</html>
"""


def build_role_html(page_id, role_name):
    page_title = f"{role_name} 詳細"
    return ROLE_PAGE_TEMPLATE.format(
        page_title=esc(page_title),
        role_name=esc(role_name),
        navigation=render_navigation(page_id),
        navigation_styles=NAV_STYLES,
    )


def build_role_pages():
    return {
        filename: build_role_html(page_id, role_name)
        for page_id, role_name, filename in ROLE_PAGES
    }
