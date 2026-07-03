#!/usr/bin/env python3
"""
Stock Swing-Trading Bot — single-run version for GitHub Actions.
Each invocation: fetches data, checks/manages position, updates state,
appends closed trades to trade_log.csv, and writes dashboard_data.json
for the React dashboard to read.

No infinite loop here — GitHub Actions calls this script on a schedule
(see .github/workflows/trading_bot.yml), so each run does exactly one
check and exits.
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("[FATAL] yfinance is not installed. Run: pip install yfinance")
    sys.exit(1)

# ============================================================
# CONFIGURATION
# ============================================================
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "VOD.L", "BARC.L", "HSBA.L"]
INTERVAL = "1h"
LOOKBACK_PERIOD = "60d"

EMA_PERIOD = 20
RSI_PERIOD = 14
RSI_BUY_TRIGGER = 40
RSI_SELL_TRIGGER = 70

STARTING_BALANCE_GBP = 2000.0
MAX_RISK_PCT = 0.02
STOP_LOSS_PCT = 0.015

STATE_FILE = "state/trading_state.json"
TRADE_LOG_FILE = "state/trade_log.csv"
DASHBOARD_FILE = "dashboard/public/dashboard_data.json"


# ============================================================
# STATE PERSISTENCE
# ============================================================
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Could not read state file ({e}). Starting fresh.")

    return {
        "balance": STARTING_BALANCE_GBP,
        "positions": {},   # ticker -> position dict
        "last_candle_time": {},  # ticker -> last processed candle time
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "closed_trades": [],  # kept here too so the dashboard has recent history without re-reading CSV
    }


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except OSError as e:
        print(f"[ERROR] Failed to save state: {e}")


def log_trade(ticker, entry_time, exit_time, entry_price, exit_price, size, pnl_gbp, pnl_pct, exit_reason):
    os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
    file_exists = os.path.exists(TRADE_LOG_FILE)
    try:
        with open(TRADE_LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "ticker", "entry_time", "exit_time", "entry_price", "exit_price",
                    "size_shares", "pnl_gbp", "pnl_pct", "exit_reason"
                ])
            writer.writerow([
                ticker, entry_time, exit_time, f"{entry_price:.2f}", f"{exit_price:.2f}",
                f"{size:.4f}", f"{pnl_gbp:.2f}", f"{pnl_pct:.2f}", exit_reason
            ])
    except OSError as e:
        print(f"[ERROR] Failed to write trade log: {e}")


# ============================================================
# DATA FETCHING
# ============================================================
def fetch_klines(ticker: str, interval: str, period: str):
    try:
        data = yf.download(
            tickers=ticker, period=period, interval=interval,
            progress=False, auto_adjust=True, threads=False,
        )
        if data is None or data.empty:
            print(f"[WARN] Empty data for {ticker}.")
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] for c in data.columns]

        data = data.reset_index()
        time_col = "Datetime" if "Datetime" in data.columns else "Date"
        data = data.rename(columns={
            time_col: "open_time", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })
        data = data[["open_time", "open", "high", "low", "close", "volume"]].dropna()

        if data.empty:
            print(f"[WARN] Parsed data empty for {ticker}.")
            return None

        return data.reset_index(drop=True)

    except Exception as e:
        print(f"[ERROR] Failed to fetch {ticker}: {e}")
        return None


def fetch_live_price(ticker: str):
    try:
        info = yf.Ticker(ticker).fast_info
        price = info.get("last_price") if isinstance(info, dict) else info.last_price
        return float(price) if price else None
    except Exception as e:
        print(f"[WARN] Could not fetch live price for {ticker}: {e}")
        return None


# ============================================================
# INDICATORS
# ============================================================
def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.where(avg_loss != 0, 100.0)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema20"] = calculate_ema(df["close"], EMA_PERIOD)
    df["rsi14"] = calculate_rsi(df["close"], RSI_PERIOD)
    return df


# ============================================================
# STRATEGY LOGIC
# ============================================================
def get_entry_signal(df: pd.DataFrame) -> dict:
    latest, previous = df.iloc[-1], df.iloc[-2]
    price, ema = latest["close"], latest["ema20"]
    rsi_now, rsi_prev = latest["rsi14"], previous["rsi14"]

    price_above_ema = price > ema
    rsi_crossed_above_40 = (rsi_prev <= RSI_BUY_TRIGGER) and (rsi_now > RSI_BUY_TRIGGER)

    return {
        "buy_triggered": price_above_ema and rsi_crossed_above_40,
        "price": price, "ema20": ema, "rsi14": rsi_now, "rsi_prev": rsi_prev,
        "candle_time": str(latest["open_time"]),
    }


def get_exit_signal(df: pd.DataFrame) -> dict:
    latest, previous = df.iloc[-1], df.iloc[-2]
    price, ema = latest["close"], latest["ema20"]
    rsi_now, rsi_prev = latest["rsi14"], previous["rsi14"]

    price_below_ema = price < ema
    rsi_crossed_above_70 = (rsi_prev <= RSI_SELL_TRIGGER) and (rsi_now > RSI_SELL_TRIGGER)
    sell_triggered = price_below_ema or rsi_crossed_above_70

    reason = ""
    if price_below_ema and rsi_crossed_above_70:
        reason = "Price below EMA20 AND RSI overbought"
    elif price_below_ema:
        reason = "Price dropped below EMA20"
    elif rsi_crossed_above_70:
        reason = "RSI crossed above 70 (overbought)"

    return {"sell_triggered": sell_triggered, "reason": reason, "price": price}


# ============================================================
# RISK MANAGEMENT
# ============================================================
def calculate_position_size(entry_price: float, balance: float) -> dict:
    max_dollar_risk = balance * MAX_RISK_PCT
    stop_loss_price = entry_price * (1 - STOP_LOSS_PCT)
    risk_per_unit = entry_price - stop_loss_price

    position_size_shares = max_dollar_risk / risk_per_unit
    position_value = position_size_shares * entry_price

    if position_value > balance:
        position_value = balance
        position_size_shares = position_value / entry_price

    return {
        "stop_loss_price": stop_loss_price,
        "position_size_shares": position_size_shares,
        "position_value": position_value,
    }


# ============================================================
# PER-TICKER CHECK
# ============================================================
def check_ticker(ticker: str, state: dict, timestamp: str, activity_log: list):
    df = fetch_klines(ticker, INTERVAL, LOOKBACK_PERIOD)
    if df is None or len(df) < max(EMA_PERIOD, RSI_PERIOD) + 2:
        activity_log.append(f"[{ticker}] Skipped — insufficient/unavailable data.")
        return state

    df = add_indicators(df)
    live_price = fetch_live_price(ticker) or float(df.iloc[-1]["close"])

    position = state["positions"].get(ticker)

    if position is not None:
        stop_loss_price = position["stop_loss"]
        exit_reason = None

        if live_price <= stop_loss_price:
            exit_reason = "STOP_LOSS_HIT"
        else:
            exit_signal = get_exit_signal(df)
            if exit_signal["sell_triggered"]:
                exit_reason = exit_signal["reason"]

        if exit_reason:
            exit_price = live_price
            proceeds = position["size"] * exit_price
            cost_basis = position["size"] * position["entry_price"]
            pnl = proceeds - cost_basis
            pnl_pct = (pnl / cost_basis) * 100

            state["balance"] += proceeds
            state["total_trades"] += 1
            state["wins" if pnl > 0 else "losses"] += 1

            log_trade(ticker, position["entry_time"], timestamp, position["entry_price"],
                       exit_price, position["size"], pnl, pnl_pct, exit_reason)

            state["closed_trades"].append({
                "ticker": ticker, "entry_time": position["entry_time"], "exit_time": timestamp,
                "entry_price": position["entry_price"], "exit_price": exit_price,
                "size": position["size"], "pnl_gbp": pnl, "pnl_pct": pnl_pct, "reason": exit_reason,
            })
            state["closed_trades"] = state["closed_trades"][-50:]  # keep last 50

            activity_log.append(f"[{ticker}] EXIT ({exit_reason}) at £{exit_price:,.2f} | "
                                 f"P&L: £{pnl:,.2f} ({pnl_pct:+.2f}%)")
            del state["positions"][ticker]
        else:
            unrealized = (live_price - position["entry_price"]) * position["size"]
            activity_log.append(f"[{ticker}] Holding | Live £{live_price:,.2f} | "
                                 f"Entry £{position['entry_price']:,.2f} | Unrealized £{unrealized:,.2f}")

    else:
        entry_signal = get_entry_signal(df)
        current_candle_time = entry_signal["candle_time"]

        if entry_signal["buy_triggered"] and state["last_candle_time"].get(ticker) != current_candle_time:
            sizing = calculate_position_size(live_price, state["balance"])

            state["positions"][ticker] = {
                "entry_price": live_price,
                "size": sizing["position_size_shares"],
                "stop_loss": sizing["stop_loss_price"],
                "entry_time": timestamp,
            }
            state["balance"] -= sizing["position_value"]
            state["last_candle_time"][ticker] = current_candle_time

            activity_log.append(f"[{ticker}] BUY at £{live_price:,.2f} | "
                                 f"Shares: {sizing['position_size_shares']:.4f} | "
                                 f"Stop: £{sizing['stop_loss_price']:,.2f}")
        else:
            activity_log.append(f"[{ticker}] No position | £{live_price:,.2f} | "
                                 f"EMA20 £{entry_signal['ema20']:,.2f} | RSI {entry_signal['rsi14']:.1f}")

    return state


# ============================================================
# DASHBOARD JSON OUTPUT
# ============================================================
def write_dashboard_json(state: dict, timestamp: str, activity_log: list):
    equity = state["balance"] + sum(
        p["size"] * p["entry_price"] for p in state["positions"].values()
    )
    total_return_pct = ((equity - STARTING_BALANCE_GBP) / STARTING_BALANCE_GBP) * 100
    win_rate = (state["wins"] / state["total_trades"] * 100) if state["total_trades"] > 0 else 0.0

    dashboard_data = {
        "last_updated": timestamp,
        "starting_balance": STARTING_BALANCE_GBP,
        "cash_balance": round(state["balance"], 2),
        "equity": round(equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_trades": state["total_trades"],
        "wins": state["wins"],
        "losses": state["losses"],
        "win_rate": round(win_rate, 1),
        "open_positions": [
            {"ticker": t, **p} for t, p in state["positions"].items()
        ],
        "recent_closed_trades": list(reversed(state["closed_trades"][-20:])),
        "activity_log": activity_log,
        "tickers_watched": TICKERS,
    }

    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    with open(DASHBOARD_FILE, "w") as f:
        json.dump(dashboard_data, f, indent=2, default=str)

    print(f"Dashboard data written to {DASHBOARD_FILE}")


# ============================================================
# MAIN (single run)
# ============================================================
def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"=== Bot run: {timestamp} ===")

    state = load_state()
    activity_log = []

    for ticker in TICKERS:
        try:
            state = check_ticker(ticker, state, timestamp, activity_log)
        except Exception as e:
            activity_log.append(f"[{ticker}] ERROR: {e}")
            print(f"[ERROR] {ticker}: {e}")

    save_state(state)
    write_dashboard_json(state, timestamp, activity_log)

    for line in activity_log:
        print(line)

    print(f"Equity: £{state['balance'] + sum(p['size'] * p['entry_price'] for p in state['positions'].values()):,.2f}")


if __name__ == "__main__":
    main()
