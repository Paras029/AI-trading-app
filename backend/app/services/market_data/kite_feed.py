"""
Zerodha Kite Connect WebSocket feed for India stocks (NSE/BSE).
Auto-authenticates via login + TOTP, then streams ticks → Redis.
"""
import asyncio
import pyotp
import structlog
from app.core import redis_client
from app.config import settings

log = structlog.get_logger()

INDIA_TOKENS = []   # populated after login (instrument tokens for NIFTY 50, RELIANCE, etc.)
INDIA_SYMBOLS = {
    256265: "NIFTY50",
    260105: "BANKNIFTY",
    738561: "RELIANCE",
    340481: "TCS",
    408065: "INFY",
}


async def run_india_feed() -> None:
    if not settings.kite_api_key:
        log.warning("kite_key_missing — India stock feed disabled")
        return
    try:
        from kiteconnect import KiteConnect, KiteTicker
    except ImportError:
        log.error("kiteconnect not installed — India feed disabled")
        return

    kite = KiteConnect(api_key=settings.kite_api_key)

    # Auto-login flow
    try:
        import requests
        session = requests.Session()
        resp = session.post("https://kite.zerodha.com/api/login", data={
            "user_id": settings.kite_user_id,
            "password": settings.kite_password,
        })
        req_id = resp.json()["data"]["request_id"]
        totp = pyotp.TOTP(settings.kite_totp_secret).now()
        resp2 = session.post("https://kite.zerodha.com/api/twofa", data={
            "user_id": settings.kite_user_id,
            "request_id": req_id,
            "twofa_value": totp,
        })
        request_token = resp2.json()["data"]["request_token"]
        sess = kite.generate_session(request_token, api_secret=settings.kite_api_secret)
        kite.set_access_token(sess["access_token"])
        log.info("kite_login_success")
    except Exception as e:
        log.error("kite_login_failed", error=str(e))
        return

    tokens = list(INDIA_SYMBOLS.keys())
    loop = asyncio.get_event_loop()

    def on_ticks(ws, ticks):
        for tick in ticks:
            token = tick["instrument_token"]
            symbol = INDIA_SYMBOLS.get(token, str(token))
            price = tick.get("last_price", 0)
            ts = int(asyncio.get_event_loop().time() * 1000)
            candle = {"t": ts, "o": price, "h": price, "l": price, "c": price, "v": 0, "symbol": symbol, "market": "india_stocks"}
            asyncio.run_coroutine_threadsafe(
                redis_client.publish(f"ticks:{symbol}", {"symbol": symbol, "market": "india_stocks", "price": price, "ts": ts}),
                loop,
            )

    def on_connect(ws, response):
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)
        log.info("kite_ws_connected")

    ticker = KiteTicker(settings.kite_api_key, kite.access_token)
    ticker.on_ticks = on_ticks
    ticker.on_connect = on_connect
    log.info("india_feed_starting", tokens=tokens)
    ticker.connect(threaded=True)
    # Keep alive
    while True:
        await asyncio.sleep(60)
