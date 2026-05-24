from typing import Annotated, Optional
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from stockstats import wrap

from .akshare_common import fetch_tencent_ohlcv


def get_indicator(
    symbol: Annotated[str, "ticker symbol of the company (e.g. 000001 or 000001.SZ)"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
    interval: Annotated[Optional[str], "time interval (daily)"] = "daily",
    time_period: Annotated[Optional[int], "number of data points for calculation"] = 14,
    series_type: Annotated[Optional[str], "price type (close, open, high, low)"] = "close",
) -> str:
    supported_indicators = {
        "close_50_sma": "close_50_sma",
        "close_200_sma": "close_200_sma",
        "close_10_ema": "close_10_ema",
        "macd": "macd",
        "macds": "macds",
        "macdh": "macdh",
        "rsi": "rsi",
        "boll": "boll",
        "boll_ub": "boll_ub",
        "boll_lb": "boll_lb",
        "kdj_k": "kdjk",
        "kdj_d": "kdjd",
        "kdj_j": "kdjj",
        "wr": "wr",
        "cci": "cci",
        "roc": "roc",
        "vr": "vr",
    }

    indicator_descriptions = {
        "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
        "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
        "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
        "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
        "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
        "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
        "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
        "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
        "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
        "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
        "kdj_k": "KDJ-K: Fast line of the KDJ stochastic oscillator. Usage: Crosses with KDJ-D generate buy/sell signals. Tips: Most responsive of the three KDJ lines; prone to whipsaws in choppy markets.",
        "kdj_d": "KDJ-D: Slow line of the KDJ stochastic oscillator. Usage: Use as a signal line for KDJ-K crossovers. Tips: Less responsive but more reliable than KDJ-K.",
        "kdj_j": "KDJ-J: The J line is 3*K - 2*D, representing divergence. Usage: Extreme values (<0 or >100) can signal reversals. Tips: Use with K and D for confirmation.",
        "wr": "Williams %R: Momentum indicator measuring overbought/oversold levels (-100 to 0). Usage: Values below -80 indicate oversold; above -20 indicate overbought. Tips: Works best in ranging markets; can stay extreme in trends.",
        "cci": "CCI: Commodity Channel Index measures deviation from statistical mean. Usage: Values above +100 indicate overbought; below -100 indicate oversold. Tips: Works well for cyclical stocks; use with trend filters.",
        "roc": "ROC: Rate of Change measures price momentum as a percentage. Usage: Positive values indicate upward momentum; negative values indicate downward momentum. Tips: Crossing zero line can signal trend changes.",
        "vr": "VR: Volume Ratio compares rising vs falling volume. Usage: Values > 200 indicate high volume accumulation; values < 80 indicate distribution. Tips: Best used as a confirmation tool.",
    }

    if indicator not in supported_indicators:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Please choose from: {list(supported_indicators.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)
    before_str = before.strftime("%Y-%m-%d")

    end_dt = curr_date_dt
    start_dt = curr_date_dt - relativedelta(years=2)
    start_str = start_dt.strftime("%Y-%m-%d")

    try:
        df = fetch_tencent_ohlcv(symbol, start_str, curr_date)
    except Exception as e:
        return f"Error fetching stock data for {symbol}: {e}"

    if df.empty:
        return f"No data found for symbol '{symbol}' to calculate {indicator}"

    stock = wrap(df)
    stock_col = supported_indicators[indicator]
    stock[stock_col]

    stock["Date"] = stock["Date"].dt.strftime("%Y-%m-%d")

    result_data = []
    for _, row in stock.iterrows():
        date_str = row["Date"]
        if before_str <= date_str <= curr_date:
            val = row.get(stock_col)
            if pd.isna(val):
                result_data.append((date_str, "N/A"))
            else:
                result_data.append((date_str, str(round(val, 2) if isinstance(val, (int, float)) else val)))

    result_data.sort(key=lambda x: x[0])

    ind_string = ""
    for date_str, value in result_data:
        ind_string += f"{date_str}: {value}\n"

    if not ind_string:
        ind_string = "No data available for the specified date range.\n"

    result_str = (
        f"## {indicator.upper()} values from {before_str} to {curr_date}:\n\n"
        + ind_string
        + "\n\n"
        + indicator_descriptions.get(indicator, "No description available.")
    )

    return result_str
