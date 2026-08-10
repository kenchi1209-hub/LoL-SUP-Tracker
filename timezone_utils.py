from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))


def now_jst():
    return datetime.now(JST)


def parse_jst_date(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=JST)
