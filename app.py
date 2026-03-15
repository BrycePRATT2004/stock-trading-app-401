from flask import Flask, render_template, redirect, url_for, request, session
from datetime import datetime
import os
from bson import ObjectId
import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient

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

# Needed for sessions (login persistence)
# Put this in .env as SECRET_KEY=some_long_random_string
app.secret_key = os.getenv("SECRET_KEY", "dev_only_change_me")


# ----------------------------
# Helpers
# ----------------------------
def get_current_user():
    """Return the logged-in user's Mongo document, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return users_col.find_one({"_id": ObjectId(user_id)})


def get_current_cash(default: float = 0.0) -> float:
    """Return logged-in user's cash as float (safe default)."""
    user = get_current_user()
    if not user:
        return default
    return float(user.get("cash", default))


def get_current_holdings() -> dict:
    """Return logged-in user's stock holdings as dict {ticker: quantity}."""
    user = get_current_user()
    if not user:
        return {}
    return user.get("holdings", {})


# ----------------------------
# Classes (left as-is, but no longer used for cash)
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

# Create Account page (your login.html)
@app.route("/", methods=["GET"])
def create_account_page():
    return render_template("login.html")


# Register (Create Account) -> saves user in MongoDB
@app.route("/register", methods=["POST"])
def register():
    full_name = request.form.get("full_name", "").strip()
    username  = request.form.get("username", "").strip().lower()
    email     = request.form.get("email", "").strip().lower()
    password  = request.form.get("password", "")
    phone     = request.form.get("phone", "").strip()

    # Basic validation
    if not all([full_name, username, email, password, phone]):
        return render_template("login.html", error="Please fill out all fields.")

    if len(password) < 6:
        return render_template("login.html", error="Password must be at least 6 characters.")

    # Check duplicates
    existing = users_col.find_one({"$or": [{"username": username}, {"email": email}]})
    if existing:
        return render_template("login.html", error="Username or email already exists. Try another.")

    # Hash password
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    users_col.insert_one({
        "full_name": full_name,
        "username": username,
        "email": email,
        "phone": phone,
        "password_hash": password_hash,  # stored as bytes
        "created_at": datetime.utcnow(),
        "role": "user",
        "cash": 1000.42,
        "holdings": {}  # {ticker: quantity}
    })

    # After create account -> send to Login page
    return redirect(url_for("login_page"))


# Login page (your register.html is the login UI)
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("register.html")

    # POST: authenticate
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

    # bcrypt check
    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        return render_template("register.html", error="Invalid username or password.")

    # ✅ success: create session
    session["user_id"] = str(user["_id"])
    session["username"] = user.get("username", "Explorer")
    session["full_name"] = user.get("full_name", "")
    session["role"] = user.get("role", "user")
    return redirect(url_for("dashboard"))


# Dashboard (protected)
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    username = session.get("username", "Explorer")

    # ✅ pull stocks from Mongo
    stocks = list(stocks_col.find({}, {"_id": 0}).sort("ticker", 1))

    # ✅ user's cash from Mongo (instead of hard-coded)
    cash = get_current_cash(default=0.0)
    holdings = get_current_holdings()

    # Calculate portfolio value
    total_invested = 0.00
    portfolio_value = cash
    portfolio_stocks = {}

    for ticker, shares in holdings.items():
        if shares > 0:
            stock = stocks_col.find_one({"ticker": ticker})
            if stock:
                current_value = shares * stock.get("price", 0.0)
                portfolio_value += current_value
                portfolio_stocks[ticker] = shares
                # For simplicity, we'll assume total_invested is the current value
                total_invested += current_value

    portfolio = {"cash": cash, "stocks": portfolio_stocks}
    total_return = portfolio_value - total_invested  # This is simplistic

    trade_message = None

    return render_template(
        "dashboard.html",
        username=username,
        portfolio=portfolio,
        total_invested=total_invested,
        portfolio_value=portfolio_value,
        total_return=total_return,
        trade_message=trade_message,
        stocks=stocks,  # ✅ pass to template
        cash=cash        # ✅ optional: use directly in dashboard.html
    )


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# Quick Mongo test
@app.route("/test-db")
def test_db():
    client.admin.command("ping")
    return "✅ MongoDB connected (ping ok)"


# ----------------------------
# Additional pages (protected)
# ----------------------------

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

    # ✅ user's cash from Mongo (instead of account.cash)
    cash = get_current_cash(default=0.0)
    holdings = get_current_holdings()

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        ticker = request.form.get("ticker", "").strip().upper()
        shares_raw = request.form.get("shares", "").strip()
        price_raw = request.form.get("price", "").strip()

        # Validation
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

        # Check if stock exists
        stock = stocks_col.find_one({"ticker": ticker})
        if not stock:
            return render_template("buy.html", cash=cash, error="Stock not found. Please check the ticker.")

        # Update user cash and holdings
        user_id = ObjectId(session["user_id"])
        users_col.update_one(
            {"_id": user_id},
            {
                "$inc": {"cash": -total_cost},
                "$inc": {f"holdings.{ticker}": shares}
            }
        )

        # Record the trade
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

    # Validation
    try:
        shares = int(shares_raw)
        price = float(price_raw)
        if shares <= 0 or price <= 0:
            raise ValueError()
    except ValueError:
        return redirect(url_for("sell"))

    if ticker not in holdings or holdings[ticker] < shares:
        return redirect(url_for("sell"))

    # Get stock info
    stock = stocks_col.find_one({"ticker": ticker})
    if not stock:
        return redirect(url_for("sell"))

    total_proceeds = shares * price

    # Update user cash and holdings
    user_id = ObjectId(session["user_id"])
    users_col.update_one(
        {"_id": user_id},
        {
            "$inc": {"cash": total_proceeds},
            "$inc": {f"holdings.{ticker}": -shares}
        }
    )

    # Record the trade
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

    return render_template(
        "wallet.html",
        cash=cash,
        stock_value=stock_value,
        total_value=total_value
    )


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

        # Validation
        if not ticker or not name or not price_raw:
            return render_template("admin.html", error="All fields are required.")

        try:
            price = float(price_raw)
            if price <= 0:
                raise ValueError()
        except ValueError:
            return render_template("admin.html", error="Price must be a positive number.")

        # ✅ Create or update the stock (upsert)
        stocks_col.update_one(
            {"ticker": ticker},
            {
                "$set": {
                    "ticker": ticker,
                    "name": name,
                    "price": price,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

        return redirect(url_for("admin"))

    # GET: show existing stocks on the page
    stocks = list(stocks_col.find({}, {"_id": 0}).sort("ticker", 1))
    return render_template("admin.html", stocks=stocks)


if __name__ == "__main__":
    app.run(debug=True)