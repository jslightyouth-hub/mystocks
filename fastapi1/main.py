from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from stock_service import (
    get_daily_stock,
    get_previous_day_bottom_movers,
    get_previous_day_top_movers,
    get_today,
)


app = FastAPI()


# Allow the Vite frontend on port 5173 to request this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/stock/{ts_code}")
def get_stock(ts_code: str):
    # Keep the route thin: date and Tushare querying live in stock_service.py.
    today = get_today()
    stock = get_daily_stock(ts_code, today)

    if stock is None:
        raise HTTPException(status_code=404, detail=f"No stock data found for {today}")

    return stock


@app.get("/stocks/top-movers")
def get_top_movers(limit: int = 50):
    return get_previous_day_top_movers(limit)


@app.get("/stocks/bottom-movers")
def get_bottom_movers(limit: int = 50):
    return get_previous_day_bottom_movers(limit)
