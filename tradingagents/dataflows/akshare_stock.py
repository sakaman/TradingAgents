from typing import Annotated
from datetime import datetime

from .akshare_common import fetch_tencent_ohlcv


def get_stock(
    symbol: Annotated[str, "ticker symbol of the company (e.g. 000001 or 000001.SZ)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    try:
        df = fetch_tencent_ohlcv(symbol, start_date, end_date)
    except Exception as e:
        return f"Error fetching stock data for {symbol}: {e}"

    if df.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].round(2)

    csv_string = df.to_csv(index=False)
    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string
