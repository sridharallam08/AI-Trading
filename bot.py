"""
RSI-based automated trading bot for stocks and crypto using Alpaca paper trading.

Runs every minute. Buys when RSI < 30 (oversold), sells when RSI > 70 (overbought).
"""

import time
import logging
import pandas as pd
from datetime import datetime, timezone
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from config import API_KEY, API_SECRET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# --- Settings ---
STOCKS = ["AAPL", "TSLA", "SPY"]
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
TRADE_QTY_STOCKS = 1       # shares per trade
CHECK_INTERVAL = 60        # seconds

# --- Clients ---
trading = TradingClient(API_KEY, API_SECRET, paper=True)
stock_data = StockHistoricalDataClient(API_KEY, API_SECRET)


def compute_rsi(closes: pd.Series, period: int = RSI_PERIOD) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)


def get_stock_rsi(symbol: str) -> float | None:
    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            limit=RSI_PERIOD + 5,
        )
        bars = stock_data.get_stock_bars(req).df
        closes = bars["close"].reset_index(drop=True)
        return compute_rsi(closes)
    except Exception as e:
        log.warning(f"Could not fetch stock bars for {symbol}: {e}")
        return None



def has_position(symbol: str) -> bool:
    try:
        # Alpaca stores crypto positions with / replaced by nothing e.g. BTCUSD
        clean = symbol.replace("/", "")
        trading.get_open_position(clean)
        return True
    except Exception:
        return False


def place_order(symbol: str, side: OrderSide, qty: float, asset_class: str):
    clean = symbol.replace("/", "")
    try:
        req = MarketOrderRequest(
            symbol=clean,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC,
        )
        order = trading.submit_order(req)
        log.info(f"ORDER PLACED | {side.value.upper()} {qty} {symbol} | id={order.id}")
    except Exception as e:
        log.error(f"Order failed for {symbol}: {e}")


def run_once():
    log.info("--- Checking RSI signals ---")

    for symbol in STOCKS:
        rsi = get_stock_rsi(symbol)
        if rsi is None:
            continue
        log.info(f"{symbol} RSI: {rsi}")
        if rsi < RSI_OVERSOLD and not has_position(symbol):
            log.info(f"BUY signal: {symbol} oversold (RSI {rsi})")
            place_order(symbol, OrderSide.BUY, TRADE_QTY_STOCKS, "stock")
        elif rsi > RSI_OVERBOUGHT and has_position(symbol):
            log.info(f"SELL signal: {symbol} overbought (RSI {rsi})")
            place_order(symbol, OrderSide.SELL, TRADE_QTY_STOCKS, "stock")



def main():
    log.info("RSI Trading Bot started (paper trading)")
    log.info(f"Stocks: {STOCKS}")
    log.info(f"RSI buy < {RSI_OVERSOLD} | RSI sell > {RSI_OVERBOUGHT} | Interval: {CHECK_INTERVAL}s")
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
