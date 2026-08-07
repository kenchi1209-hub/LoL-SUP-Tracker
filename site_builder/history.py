"""独立した Match History ページを生成する。"""

from site_builder.render import (
    load_template,
    page_header_context,
    render_match_history,
    render_navigation,
)


HISTORY_PAGE_TEMPLATE = load_template("history.html")


def build_history_html(rows, version):
    return HISTORY_PAGE_TEMPLATE.format(
        **page_header_context(rows),
        navigation=render_navigation("history"),
        match_history=render_match_history(rows, version, "top"),
    )
