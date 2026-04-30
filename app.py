from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from datetime import datetime
import os
from bson import ObjectId
import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient
import random
import threading
import time
from zoneinfo import ZoneInfo

# ----------------------------
# Mongo setup
# ----------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set. Check your .env file.")

client = MongoClient(MONGO_URI)
db = client["stock_trading_app_401"]
users_col = db["users"]
stocks_col = db["stocks"]
trades_col = db["trades"]

# ----------------------------
# Flask app
# ----------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_only_change_me")

# ----------------------------
# Market Hours
# ----------------------------
ET = ZoneInfo("America/New_York")

def is_market_open():
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    return 9 <= now.hour < 16

# ----------------------------
# Stock Ticker System
# ----------------------------
ticker_state = {}
ticker_lock = threading.Lock()

def initialize_ticker_state():
    stocks = list(stocks_col.find({}, {"_id": 0}))
    for stock in stocks:
        ticker = stock.get("ticker")
        if ticker and ticker not in ticker_state:
            price = stock.get("price", 0.0)
            ticker_state[ticker] = {
                "ticker": ticker,
                "current_price": price,
                "opening_price": price,
                "daily_high": price,
                "daily_low": price,
                "daily_change": 0.0,
                "daily_change_percent": 0.0,
            }

def update_ticker_prices():
    with ticker_lock:
        for ticker in ticker_state:
            state = ticker_state[ticker]
            current_price = state["current_price"]
            change_percent = random.uniform(-2, 2) / 100
            new_price = max(0.01, round(current_price * (1 + change_percent), 2))
            state["current_price"] = new_price
            state["daily_high"] = max(state["daily_high"], new_price)
            state["daily_low"] = min(state["daily_low"], new_price)
            state["daily_change"] = round(new_price - state["opening_price"], 2)
            if state["opening_price"] > 0:
                state["daily_change_percent"] = round(
                    ((new_price - state["opening_price"]) / state["opening_price"]) * 100, 2
                )

def reset_opening_prices():
    with ticker_lock:
        for ticker in ticker_state:
            state = ticker_state[ticker]
            price = state["current_price"]
            state["opening_price"] = price
            state["daily_high"] = price
            state["daily_low"] = price
            state["daily_change"] = 0.0
            state["daily_change_percent"] = 0.0

def get_ticker_data():
    with ticker_lock:
        return list(ticker_state.values())

# ----------------------------
# Background price update thread (runs 24/7)
# ----------------------------
last_market_state = None

def price_update_loop():
    global last_market_state
    while True:
        if not ticker_state:
            initialize_ticker_state()

        # Reset opening prices when market transitions closed -> open
        open_now = is_market_open()
        if open_now and last_market_state is False:
            reset_opening_prices()
            process_pending_orders()
        elif open_now and last_market_state is None:
            process_pending_orders()
        last_market_state = open_now

        # Always update prices regardless of market hours
        update_ticker_prices()
        time.sleep(5)

def start_price_thread():
    t = threading.Thread(target=price_update_loop, daemon=True)
    t.start()

def process_pending_orders():
    pending_orders = list(trades_col.find({"status": "pending"}).sort("created_at", 1))
    if not pending_orders:
        return

    for order in pending_orders:
        user_id = order["user_id"]
        user = users_col.find_one({"_id": user_id})
        if not user:
            trades_col.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "failed", "failed_reason": "User not found at execution", "executed_at": datetime.utcnow()}}
            )
            continue

        ticker = order.get("ticker")
        shares = int(order.get("shares", 0))
        stock_state = ticker_state.get(ticker)
        execution_price = None

        if stock_state:
            execution_price = float(stock_state.get("current_price", 0.0))
        else:
            stock_doc = stocks_col.find_one({"ticker": ticker})
            execution_price = float(stock_doc.get("price", 0.0)) if stock_doc else None

        if execution_price is None or execution_price <= 0:
            trades_col.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "failed", "failed_reason": "Could not determine execution price", "executed_at": datetime.utcnow()}}
            )
            continue

        if order["type"] == "buy":
            cash = float(user.get("cash", 0.0))
            total_cost = round(execution_price * shares, 2)
            if cash >= total_cost:
                users_col.update_one(
                    {"_id": user_id},
                    {"$inc": {"cash": -total_cost, f"holdings.{ticker}": shares}}
                )
                trades_col.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"status": "completed", "price": execution_price, "total_proceeds": total_cost, "executed_at": datetime.utcnow()}}
                )
            else:
                trades_col.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"status": "failed", "failed_reason": "Insufficient funds at market open", "executed_at": datetime.utcnow()}}
                )
        else:
            holdings = user.get("holdings", {}) or {}
            if holdings.get(ticker, 0) >= shares:
                total_proceeds = round(execution_price * shares, 2)
                users_col.update_one(
                    {"_id": user_id},
                    {"$inc": {"cash": total_proceeds, f"holdings.{ticker}": -shares}}
                )
                trades_col.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"status": "completed", "price": execution_price, "total_proceeds": total_proceeds, "executed_at": datetime.utcnow()}}
                )
            else:
                trades_col.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"status": "failed", "failed_reason": "Insufficient holdings at market open", "executed_at": datetime.utcnow()}}
                )


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return users_col.find_one({"_id": ObjectId(user_id)})

def get_current_cash(default: float = 0.0) -> float:
    user = get_current_user()
    if not user:
        return default
    return float(user.get("cash", default))

def get_current_holdings() -> dict:
    user = get_current_user()
    if not user:
        return {}
    return user.get("holdings", {})

# ----------------------------
# Classes (unused but kept)
# ----------------------------
class Account:
    pass

class User:
    pass

class Trade:
    pass

class GetPrices:
    pass

# ----------------------------
# Routes
# ----------------------------

@app.route("/", methods=["GET"])
def create_account_page():
    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():
    full_name = request.form.get("full_name", "").strip()
    username  = request.form.get("username", "").strip().lower()
    email     = request.form.get("email", "").strip().lower()
    password  = request.form.get("password", "")
    phone     = request.form.get("phone", "").strip()

    if not all([full_name, username, email, password, phone]):
        return render_template("login.html", error="Please fill out all fields.")

    if len(password) < 6:
        return render_template("login.html", error="Password must be at least 6 characters.")

    existing = users_col.find_one({"$or": [{"username": username}, {"email": email}]})
    if existing:
        return render_template("login.html", error="Username or email already exists. Try another.")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    users_col.insert_one({
        "full_name": full_name,
        "username": username,
        "email": email,
        "phone": phone,
        "password_hash": password_hash,
        "created_at": datetime.utcnow(),
        "role": "user",
        "cash": 1000.42,
        "holdings": {}
    })

    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("register.html", error="Please enter username and password.")

    user = users_col.find_one({"username": username})
    if not user:
        return render_template("register.html", error="Invalid username or password.")

    stored_hash = user.get("password_hash")
    if not stored_hash:
        return render_template("register.html", error="Account error: missing password hash.")

    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        return render_template("register.html", error="Invalid username or password.")

    session["user_id"] = str(user["_id"])
    session["username"] = user.get("username", "Explorer")
    session["full_name"] = user.get("full_name", "")
    session["role"] = user.get("role", "user")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    username = session.get("username", "Explorer")
    stocks = list(stocks_col.find({}, {"_id": 0}).sort("ticker", 1))
    cash = get_current_cash(default=0.0)
    holdings = get_current_holdings()

    total_invested = 0.00
    portfolio_value = cash
    portfolio_stocks = {}
    total_opening_value = cash
    total_portfolio_change = 0.0

    for ticker, shares in holdings.items():
        if shares > 0:
            with ticker_lock:
                ticker_info = ticker_state.get(ticker)
            if ticker_info:
                current_price = float(ticker_info.get("current_price", 0.0))
                opening_price = float(ticker_info.get("opening_price", 0.0))
            else:
                stock = stocks_col.find_one({"ticker": ticker})
                current_price = float(stock.get("price", 0.0)) if stock else 0.0
                opening_price = current_price

            current_value = shares * current_price
            opening_value = shares * opening_price
            portfolio_value += current_value
            total_invested += current_value
            total_opening_value += opening_value
            total_portfolio_change += current_value - opening_value
            portfolio_stocks[ticker] = shares

    if total_opening_value > 0:
        total_portfolio_change_pct = (total_portfolio_change / total_opening_value) * 100
    else:
        total_portfolio_change_pct = 0.0

    portfolio = {"cash": cash, "stocks": portfolio_stocks}
    total_return = portfolio_value - total_invested
    trade_message = None

    return render_template(
        "dashboard.html",
        username=username,
        portfolio=portfolio,
        total_invested=total_invested,
        portfolio_value=portfolio_value,
        total_return=total_return,
        total_portfolio_change=total_portfolio_change,
        total_portfolio_change_pct=total_portfolio_change_pct,
        trade_message=trade_message,
        stocks=stocks,
        cash=cash
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/test-db")
def test_db():
    client.admin.command("ping")
    return "✅ MongoDB connected (ping ok)"


@app.route("/trade-history")
def trade_history():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    user_id = ObjectId(session["user_id"])
    orders = list(trades_col.find({"user_id": user_id}).sort("created_at", -1))
    return render_template("trade_history.html", orders=orders)


@app.route("/buy", methods=["GET", "POST"])
def buy():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    cash = get_current_cash(default=0.0)

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        ticker = request.form.get("ticker", "").strip().upper()
        shares_raw = request.form.get("shares", "").strip()
        price_raw = request.form.get("price", "").strip()
        pending_confirm = request.form.get("pending_confirm") == "yes"

        try:
            shares = int(shares_raw)
            price = float(price_raw)
            if shares <= 0 or price <= 0:
                raise ValueError()
        except ValueError:
            return render_template("buy.html", cash=cash, error="Invalid shares or price.")

        total_cost = shares * price

        if total_cost > cash:
            return render_template("buy.html", cash=cash, error="Insufficient funds.")

        stock = stocks_col.find_one({"ticker": ticker})
        if not stock:
            return render_template("buy.html", cash=cash, error="Stock not found.")

        if not is_market_open() and not pending_confirm:
            pending_data = {
                "company": company,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "total_cost": total_cost,
            }
            return render_template("buy.html", cash=cash, pending_data=pending_data, market_closed=True)

        user_id = ObjectId(session["user_id"])

        if not is_market_open() and pending_confirm:
            trades_col.insert_one({
                "user_id": user_id,
                "type": "buy",
                "company": company,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "requested_price": price,
                "requested_total": total_cost,
                "total_proceeds": total_cost,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "pending_at": datetime.utcnow()
            })
            return render_template("buy.html", cash=cash, success=True, pending=True)

        users_col.update_one(
            {"_id": user_id},
            {"$inc": {"cash": -total_cost, f"holdings.{ticker}": shares}}
        )

        trades_col.insert_one({
            "user_id": user_id,
            "type": "buy",
            "company": company,
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "total_proceeds": total_cost,
            "status": "completed",
            "created_at": datetime.utcnow()
        })

        return render_template("buy.html", cash=cash - total_cost, success=True)

    return render_template("buy.html", cash=cash)


@app.route("/sell", methods=["GET"])
def sell():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    holdings = get_current_holdings()
    portfolio = {}

    for ticker, shares in holdings.items():
        if shares > 0:
            stock = stocks_col.find_one({"ticker": ticker})
            if stock:
                portfolio[ticker] = {
                    "company": stock.get("name", ticker),
                    "shares": shares
                }

    return render_template("sell.html", portfolio=portfolio)


@app.route("/sell_post", methods=["POST"])
def sell_post():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    holdings = get_current_holdings()
    ticker = request.form.get("ticker", "").strip().upper()
    shares_raw = request.form.get("shares", "").strip()
    price_raw = request.form.get("price", "").strip()
    pending_confirm = request.form.get("pending_confirm") == "yes"

    try:
        shares = int(shares_raw)
        price = float(price_raw)
        if shares <= 0 or price <= 0:
            raise ValueError()
    except ValueError:
        return redirect(url_for("sell"))

    if ticker not in holdings or holdings[ticker] < shares:
        return redirect(url_for("sell"))

    stock = stocks_col.find_one({"ticker": ticker})
    if not stock:
        return redirect(url_for("sell"))

    total_proceeds = shares * price

    if not is_market_open() and not pending_confirm:
        pending_data = {
            "company": stock.get("name", ticker),
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "total_proceeds": total_proceeds,
        }
        portfolio = {}
        for t, s in holdings.items():
            if s > 0:
                stock_info = stocks_col.find_one({"ticker": t})
                if stock_info:
                    portfolio[t] = {"company": stock_info.get("name", t), "shares": s}
        return render_template("sell.html", portfolio=portfolio, market_closed=True, pending_data=pending_data)

    user_id = ObjectId(session["user_id"])

    if not is_market_open() and pending_confirm:
        trades_col.insert_one({
            "user_id": user_id,
            "type": "sell",
            "company": stock.get("name", ticker),
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "requested_price": price,
            "requested_total": total_proceeds,
            "total_proceeds": total_proceeds,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "pending_at": datetime.utcnow()
        })
        portfolio = {}
        for t, s in holdings.items():
            if s > 0:
                stock_info = stocks_col.find_one({"ticker": t})
                if stock_info:
                    portfolio[t] = {"company": stock_info.get("name", t), "shares": s}
        return render_template("sell.html", portfolio=portfolio, success=True, pending=True)

    user_id = ObjectId(session["user_id"])
    users_col.update_one(
        {"_id": user_id},
        {"$inc": {"cash": total_proceeds, f"holdings.{ticker}": -shares}}
    )

    trades_col.insert_one({
        "user_id": user_id,
        "type": "sell",
        "company": stock.get("name", ticker),
        "ticker": ticker,
        "shares": shares,
        "price": price,
        "total_proceeds": total_proceeds,
        "status": "completed",
        "created_at": datetime.utcnow()
    })

    return redirect(url_for("sell"))


@app.route("/wallet")
def wallet():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    cash = get_current_cash(default=0.0)
    holdings = get_current_holdings()

    stock_value = 0.0
    for ticker, shares in holdings.items():
        if shares > 0:
            stock = stocks_col.find_one({"ticker": ticker})
            if stock:
                stock_value += shares * stock.get("price", 0.0)

    total_value = cash + stock_value
    return render_template("wallet.html", cash=cash, stock_value=stock_value, total_value=total_value)


@app.route("/wallet/deposit", methods=["POST"])
def wallet_deposit():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    amount_raw = request.form.get("amount", "").strip()

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        return redirect(url_for("wallet"))

    users_col.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$inc": {"cash": amount}}
    )

    return redirect(url_for("wallet"))


@app.route("/wallet/withdraw", methods=["POST"])
def wallet_withdraw():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    amount_raw = request.form.get("amount", "").strip()
    cash = get_current_cash(default=0.0)

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        return redirect(url_for("wallet"))

    # Check if user has sufficient funds
    if amount > cash:
        return redirect(url_for("wallet"))

    users_col.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$inc": {"cash": -amount}}
    )

    return redirect(url_for("wallet"))


@app.route("/help")
def help_page():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("help.html")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("role") != "admin":
        return "Forbidden", 403

    if request.method == "POST":
        ticker = request.form.get("ticker", "").strip().upper()
        name = request.form.get("name", "").strip()
        price_raw = request.form.get("price", "").strip()

        if not ticker or not name or not price_raw:
            return render_template("admin.html", error="All fields are required.")

        try:
            price = float(price_raw)
            if price <= 0:
                raise ValueError()
        except ValueError:
            return render_template("admin.html", error="Price must be a positive number.")

        stocks_col.update_one(
            {"ticker": ticker},
            {
                "$set": {"ticker": ticker, "name": name, "price": price, "updated_at": datetime.utcnow()},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

        with ticker_lock:
            if ticker not in ticker_state:
                ticker_state[ticker] = {
                    "ticker": ticker,
                    "current_price": price,
                    "opening_price": price,
                    "daily_high": price,
                    "daily_low": price,
                    "daily_change": 0.0,
                    "daily_change_percent": 0.0,
                }

        return redirect(url_for("admin"))

    stocks = list(stocks_col.find({}, {"_id": 0}).sort("ticker", 1))
    return render_template("admin.html", stocks=stocks)

@app.route("/admin/delete", methods=["POST"])
def delete_stock():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("role") != "admin":
        return "Forbidden", 403

    ticker = request.form.get("ticker", "").strip().upper()
    if ticker:
        stocks_col.delete_one({"ticker": ticker})
        with ticker_lock:
            ticker_state.pop(ticker, None)

    stocks = list(stocks_col.find({}, {"_id": 0}).sort("ticker", 1))
    return render_template("admin.html", stocks=stocks, success=True)


# ----------------------------
# API Endpoints
# ----------------------------

@app.route("/api/ticker")
def api_ticker():
    data = get_ticker_data()
    return jsonify({
        "market_open": is_market_open(),
        "stocks": data
    })


if __name__ == "__main__":
    initialize_ticker_state()
    start_price_thread()
    app.run(debug=True)