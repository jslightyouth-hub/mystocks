from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from stock_service import (
    get_daily_stock,
    get_industry_movers_rankings,
    get_industry_stocks_rankings,
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
def get_top_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_top_movers(page, page_size)


@app.get("/stocks/bottom-movers")
def get_bottom_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_bottom_movers(page, page_size)


@app.get("/industries/movers")
def get_industry_movers(exclude_high: int = 1, exclude_low: int = 1):
    return get_industry_movers_rankings(exclude_high, exclude_low)


@app.get("/industries/l3/movers")
def get_l3_industry_movers(exclude_high: int = 1, exclude_low: int = 1):
    return get_industry_movers_rankings(exclude_high, exclude_low, level="l3")


@app.get("/industries/l3/{industry_name}/stocks")
def get_l3_industry_stocks(industry_name: str, limit: int = 10):
    return get_industry_stocks_rankings(industry_name, limit, level="l3")


@app.get("/industries/{industry_name}/stocks")
def get_industry_stocks(industry_name: str, limit: int = 10):
    return get_industry_stocks_rankings(industry_name, limit)
