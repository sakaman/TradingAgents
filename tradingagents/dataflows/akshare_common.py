import time
import logging
import requests
import pandas as pd

logger = logging.getLogger(__name__)

TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

CHINESE_COLUMN_MAP = {
    "日期": "Date",
    "开盘": "Open",
    "收盘": "Close",
    "最高": "High",
    "最低": "Low",
    "成交量": "Volume",
    "成交额": "Amount",
    "振幅": "Amplitude",
    "涨跌幅": "ChangePct",
    "涨跌额": "Change",
    "换手率": "Turnover",
    "股票代码": "Symbol",
    "股票简称": "Name",
    "上市日期": "ListDate",
    "注册资本": "RegisteredCapital",
    "所属行业": "Industry",
    "总股本": "TotalShares",
    "流通股": "FloatShares",
    "总市值": "TotalMarketCap",
    "流通市值": "FloatMarketCap",
    "营业收入": "Revenue",
    "净利润": "NetProfit",
    "每股净资产": "BookValuePerShare",
    "每股收益": "EPS",
    "每股经营现金流": "CashFlowPerShare",
    "净资产收益率": "ROE",
    "总资产": "TotalAssets",
    "流动资产": "CurrentAssets",
    "流动负债": "CurrentLiabilities",
    "资产负债率": "DebtRatio",
    "股东人数": "ShareholderCount",
}

def convert_symbol_to_akshare(symbol: str) -> str:
    stripped = symbol.upper()
    for suffix in (".SS", ".SZ"):
        if stripped.endswith(suffix):
            return stripped[: -len(suffix)]
    return stripped


def _tencent_prefix(symbol: str) -> str:
    code = convert_symbol_to_akshare(symbol)
    if code.startswith("6"):
        return "sh"
    return "sz"


def convert_symbol_to_tencent(symbol: str) -> str:
    code = convert_symbol_to_akshare(symbol)
    prefix = _tencent_prefix(symbol)
    return f"{prefix}{code}"


def akshare_retry(func, max_retries=3, base_delay=2.0):
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"AKShare call failed, retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )
                time.sleep(delay)
            else:
                raise


def normalize_ohlcv_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=CHINESE_COLUMN_MAP)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
    numeric_cols = ["Open", "High", "Low", "Close", "Volume", "Amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_tencent_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    tencent_sym = convert_symbol_to_tencent(symbol)
    params = {
        "param": f"{tencent_sym},day,{start_date},{end_date},2000,qfq",
    }
    resp = requests.get(TENCENT_KLINE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"Tencent API error: {data.get('msg', 'unknown')}")

    records = data.get("data", {}).get(tencent_sym, {}).get("qfqday", [])
    if not records:
        return pd.DataFrame()

    rows = []
    for r in records:
        rows.append({
            "Date": r[0],
            "Open": float(r[1]),
            "Close": float(r[2]),
            "High": float(r[3]),
            "Low": float(r[4]),
            "Volume": float(r[5]),
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    price_cols = ["Open", "High", "Low", "Close", "Volume"]
    for c in price_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df
