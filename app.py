from decimal import Decimal
from flask import Flask, render_template, redirect, url_for, request, session
from datetime import datetime
import os

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
# ----------------------------
# Flask app
# ----------------------------
app = Flask(__name__)

# Needed for sessions (login persistence)
# Put this in .env as SECRET_KEY=some_long_random_string
app.secret_key = os.getenv("SECRET_KEY", "dev_only_change_me")

# ----------------------------
# ----------------------------
class Account:
    pass
    def __init__(self, cash):
        self.cash = Decimal(cash)

account = Account("1000.12")
print(f"${account.cash:,.2f}")

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
        "role" : "user",
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

    portfolio = {"cash": 10000.00, "stocks": {}}
    total_invested = 0.00
    portfolio_value = portfolio["cash"]
    total_return = 0.00
    trade_message = None

    return render_template(
        "dashboard.html",
        username=username,
        portfolio=portfolio,
        total_invested=total_invested,
        portfolio_value=portfolio_value,
        total_return=total_return,
        trade_message=trade_message,
        stocks=stocks  # ✅ pass to template
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

    return render_template("trade_history.html")


@app.route("/buy", methods=["GET", "POST"])
def buy():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        # TODO: process order here (for now just pretend success)
        return render_template("buy.html", cash=float(account.cash), success=True)

    return render_template("buy.html", cash=float(account.cash))


@app.route("/sell")
def sell():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    
    return render_template("sell.html")

@app.route("/wallet")
def wallet():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    stock_value = Decimal("1250.00")   # placeholder for now
    total_value = account.cash + stock_value

    return render_template(
        "wallet.html",
        cash=account.cash,
        stock_value=stock_value,
        total_value=total_value
    )


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