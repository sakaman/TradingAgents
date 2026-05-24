from typing import Annotated, Optional
from datetime import datetime, timedelta

from .akshare_common import convert_symbol_to_akshare


def get_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "end date in YYYY-MM-DD format"],
) -> str:
    akshare_symbol = convert_symbol_to_akshare(ticker)

    return (
        f"## {ticker} News, from {start_date} to {end_date}:\n\n"
        f"News for A-share stocks is available from East Money.\n"
        f"Symbol: {akshare_symbol}\n"
        f"Search URL: https://so.eastmoney.com/news/s?keyword={akshare_symbol}\n"
        f"For detailed news, please visit the above link.\n"
    )


def get_global_news(
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
    look_back_days: Annotated[Optional[int], "days to look back"] = None,
    limit: Annotated[Optional[int], "max articles to return"] = None,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days or 7)
    start_date = start_dt.strftime("%Y-%m-%d")

    return (
        f"## China A-Share Market News, from {start_date} to {curr_date}:\n\n"
        f"Global market news for A-share investors:\n"
        f"- East Money News: https://so.eastmoney.com/news/s?keyword=A股\n"
        f"- Sina Finance: https://finance.sina.com.cn/\n"
        f"- For macro news and policy updates, visit the above sources.\n"
    )
