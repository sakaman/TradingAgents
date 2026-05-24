import re
from typing import Annotated
from datetime import datetime
from io import StringIO

import requests
import pandas as pd
from parsel import Selector

from .akshare_common import convert_symbol_to_akshare, akshare_retry

SINA_NC_URL = "https://finance.sina.com.cn/realstock/company/sh{nc}/nc.shtml"
SINA_FINANCE_URL = "https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_{report_type}/stockid/{code}/ctrl/part/displaytype/4.phtml"


def _numeric_code(symbol: str) -> str:
    return convert_symbol_to_akshare(symbol)


def _sina_code(symbol: str) -> str:
    code = _numeric_code(symbol)
    prefix = "sh" if code.startswith("6") else "sz"
    return f"{prefix}{code}"


def _scrape_sina_nc(symbol: str) -> dict:
    scode = _sina_code(symbol)
    url = f"https://finance.sina.com.cn/realstock/company/{scode}/nc.shtml"
    resp = requests.get(url, timeout=15)
    resp.encoding = "gb2312"
    html = resp.text

    vars_map = {
        "stockname": "stockname",
        "mgjzc": "BookValuePerShare",
        "fourQ_mgsy": "TTM_EPS",
        "lastyear_mgsy": "LastYear_EPS",
        "profit": "LatestAnnual_NetProfit",
        "profit_four": "TTM_NetProfit",
        "totalcapital": "TotalCapital",
        "currcapital": "FloatCapital",
        "curracapital": "FloatA_Capital",
    }

    result = {}
    for var_name, label in vars_map.items():
        m = re.search(rf"var {var_name}\s*=\s*\"?([\d.]+)\"?;", html)
        if m:
            result[label] = m.group(1)

    if "stockname" not in result:
        for field in ["mgjzc", "fourQ_mgsy", "lastyear_mgsy", "profit", "profit_four",
                      "totalcapital", "currcapital", "curracapital"]:
            m = re.search(rf"var {field}\s*=\s*([\d.]+);", html)
            if m:
                label = vars_map.get(field, field)
                result[label] = m.group(1)

    m = re.search(r'stockname\s*=\s*"([^"]+)"', html)
    if m:
        result["Name"] = m.group(1)

    return result


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company (e.g. 000001 or 000001.SZ)"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    try:
        info = akshare_retry(lambda: _scrape_sina_nc(ticker))
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {e}"

    if not info:
        return f"No fundamentals data found for symbol '{ticker}'"

    header = f"# Company Fundamentals for {ticker}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    label_map = {
        "Name": "Name",
        "BookValuePerShare": "Book Value Per Share (每股净资产)",
        "TTM_EPS": "TTM EPS (最近四个季度每股收益)",
        "LastYear_EPS": "Last Year EPS (前一年每股收益)",
        "LatestAnnual_NetProfit": "Latest Annual Net Profit (最近年度净利润, 亿元)",
        "TTM_NetProfit": "TTM Net Profit (最近四个季度净利润, 亿元)",
        "TotalCapital": "Total Capital (总股本, 万)",
        "FloatCapital": "Float Capital (流通股本, 万)",
        "FloatA_Capital": "Float A-Share Capital (流通A股, 万)",
    }

    lines = []
    for key, display in label_map.items():
        val = info.get(key)
        if val:
            lines.append(f"{display}: {val}")

    return header + "\n".join(lines)


def _scrape_sina_financial_table(symbol: str, report_type: str) -> pd.DataFrame:
    code = _numeric_code(symbol)
    url = SINA_FINANCE_URL.format(report_type=report_type, code=code)
    resp = requests.get(url, timeout=15)
    resp.encoding = "gb2312"
    sel = Selector(text=resp.text)

    tables = sel.css("table")
    target_table = None
    for table in tables:
        text = "".join(table.css("::text").getall())
        if "报表日期" in text:
            target_table = table
            break

    if target_table is None:
        return pd.DataFrame()

    header_row = None
    rows = []
    for tr in target_table.css("tr"):
        cells = [c.strip() for c in tr.css("td::text, td strong::text, td a::text, th::text").getall() if c.strip()]
        if not cells:
            continue
        if cells[0] == "报表日期" or cells[0] == "报告期":
            header_row = cells
            continue
        if header_row is not None and len(cells) == len(header_row):
            rows.append(cells)

    if not header_row or not rows:
        header_row = None
        rows = []
        for tr in target_table.css("tr"):
            cells = ["".join(td.css("::text").getall()).strip() for td in tr.css("td, th")]
            cells = [c for c in cells if c]
            if len(cells) >= 5:
                if header_row is None:
                    header_row = cells
                else:
                    rows.append(cells)

    if not header_row or not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=header_row[:len(rows[0])])
    return df


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    try:
        df = akshare_retry(lambda: _scrape_sina_financial_table(ticker, "BalanceSheet"))
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {e}"

    if df.empty:
        return f"No balance sheet data found for symbol '{ticker}'"

    df = _filter_sina_financials(df, curr_date, freq)
    csv_string = df.to_csv(index=False)
    header = f"# Balance Sheet data for {ticker} ({freq})\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    try:
        df = akshare_retry(lambda: _scrape_sina_financial_table(ticker, "CashFlow"))
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {e}"

    if df.empty:
        return f"No cash flow data found for symbol '{ticker}'"

    df = _filter_sina_financials(df, curr_date, freq)
    csv_string = df.to_csv(index=False)
    header = f"# Cash Flow data for {ticker} ({freq})\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    try:
        df = akshare_retry(lambda: _scrape_sina_financial_table(ticker, "ProfitStatement"))
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {e}"

    if df.empty:
        return f"No income statement data found for symbol '{ticker}'"

    df = _filter_sina_financials(df, curr_date, freq)
    csv_string = df.to_csv(index=False)
    header = f"# Income Statement data for {ticker} ({freq})\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    code = _numeric_code(ticker)
    scode = _sina_code(ticker)

    lines = []
    lines.append(f"# Shareholder/Insider data for {ticker}")
    lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"Stock code: {code}")
    lines.append("")
    lines.append("Shareholder information is available from:")
    lines.append(f"  - Sina Finance: https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_StockHolder/stockid/{code}.phtml")
    lines.append(f"  - East Money: https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/Index?type=web&code={scode}")

    return "\n".join(lines)


def _filter_sina_financials(df: pd.DataFrame, curr_date: str, freq: str) -> pd.DataFrame:
    keep_cols = [df.columns[0]]
    date_cols = []
    for col in df.columns[1:]:
        try:
            dt = pd.to_datetime(col, format="%Y-%m-%d", errors="coerce")
        except (ValueError, TypeError):
            dt = pd.NaT
        if pd.isna(dt):
            continue
        if curr_date and dt > pd.Timestamp(curr_date):
            continue
        if freq == "annual" and dt.month != 12:
            continue
        date_cols.append((dt, col))

    date_cols.sort(key=lambda x: x[0], reverse=True)
    keep_cols.extend(c for _, c in date_cols)
    return df[keep_cols]
