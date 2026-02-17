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
        "created_at": datetime.utcnow()
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

    return redirect(url_for("dashboard"))

# Dashboard (protected)
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    # Minimal placeholders so your dashboard template doesn't crash
    username = session.get("username", "Explorer")

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
        trade_message=trade_message
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


@app.route("/buy")
def buy():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    from bson.objectid import ObjectId
    user_id = session.get("user_id")
    try:
        uid = ObjectId(user_id)
    except:
        return redirect(url_for("login_page"))
    
    user = users_col.find_one({"_id": uid})
    if not user:
        return redirect(url_for("login_page"))
    
    cash = user.get("cash", 0.0)
    return render_template("buy.html", cash=cash)


@app.route("/buy_post", methods=["POST"])
def buy_post():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    from bson.objectid import ObjectId
    
    user_id = session.get("user_id")
    try:
        uid = ObjectId(user_id)
    except:
        return redirect(url_for("login_page"))
    
    user = users_col.find_one({"_id": uid})
    if not user:
        return redirect(url_for("login_page"))

    company = request.form.get("company", "").strip()
    ticker = request.form.get("ticker", "").strip().upper()
    try:
        shares = int(request.form.get("shares", "0"))
    except ValueError:
        shares = 0
    try:
        price = float(request.form.get("price", "0"))
    except ValueError:
        price = 0.0

    # Validate inputs
    if not company or not ticker or shares <= 0 or price <= 0:
        cash = user.get("cash", 0.0)
        return render_template("buy.html", cash=cash, error="Please fill out all fields correctly.")

    total_cost = shares * price
    if user.get("cash", 0.0) < total_cost:
        cash = user.get("cash", 0.0)
        return render_template("buy.html", cash=cash, error=f"Insufficient funds. You need ${total_cost:.2f} but only have ${cash:.2f}.")

    # Deduct cash and add to pending orders
    users_col.update_one(
        {"_id": uid},
        {
            "$inc": {"cash": -total_cost},
            "$push": {
                "orders": {
                    "order_id": str(ObjectId()),
                    "company": company,
                    "ticker": ticker,
                    "shares": shares,
                    "price": price,
                    "total_cost": total_cost,
                    "status": "pending",
                    "type": "buy",
                    "created_at": datetime.utcnow()
                }
            }
        }
    )

    return redirect(url_for("dashboard"))


@app.route("/sell")
def sell():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
<<<<<<< HEAD
    
    return render_template("sell.html")
=======

    from bson.objectid import ObjectId
    user_id = session.get("user_id")
    try:
        uid = ObjectId(user_id)
    except:
        return redirect(url_for("login_page"))
    
    user = users_col.find_one({"_id": uid})
    if not user:
        return redirect(url_for("login_page"))
    
    portfolio = user.get("portfolio", {})
    return render_template("sell.html", portfolio=portfolio)


@app.route("/sell_post", methods=["POST"])
def sell_post():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    from bson.objectid import ObjectId
    
    user_id = session.get("user_id")
    try:
        uid = ObjectId(user_id)
    except:
        return redirect(url_for("login_page"))
    
    user = users_col.find_one({"_id": uid})
    if not user:
        return redirect(url_for("login_page"))

    ticker = request.form.get("ticker", "").strip().upper()
    try:
        shares = int(request.form.get("shares", "0"))
    except ValueError:
        shares = 0
    try:
        price = float(request.form.get("price", "0"))
    except ValueError:
        price = 0.0

    # Validate inputs
    portfolio = user.get("portfolio", {})
    if not ticker or ticker not in portfolio:
        return render_template("sell.html", portfolio=portfolio, error="Please select a valid stock.")
    
    holding = portfolio.get(ticker, {})
    max_shares = holding.get("shares", 0)
    
    if shares <= 0 or price <= 0:
        return render_template("sell.html", portfolio=portfolio, error="Please fill out all fields correctly.")
    
    if shares > max_shares:
        return render_template("sell.html", portfolio=portfolio, error=f"You cannot sell more than {max_shares} shares of {ticker}.")

    total_proceeds = shares * price
    
    # Update portfolio and add cash
    holding["shares"] -= shares
    if holding["shares"] == 0:
        portfolio.pop(ticker, None)
    
    users_col.update_one(
        {"_id": uid},
        {
            "$inc": {"cash": total_proceeds},
            "$set": {"portfolio": portfolio},
            "$push": {
                "orders": {
                    "order_id": str(ObjectId()),
                    "company": holding.get("company", ""),
                    "ticker": ticker,
                    "shares": shares,
                    "price": price,
                    "total_proceeds": total_proceeds,
                    "status": "executed",
                    "type": "sell",
                    "created_at": datetime.utcnow()
                }
            }
        }
    )

    return redirect(url_for("dashboard"))
>>>>>>> 67ed0446f4e7de8385e4a13deff4b037c7a67cb0

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
 
@app.post("/wallet/deposit")
def wallet_deposit():
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401

    amount_str = (request.form.get("amount") or "").strip()

    try:
        amount = Decimal(amount_str)
    except (InvalidOperation, ValueError):
        return redirect(url_for("wallet"))  # or flash an error

    # basic validation
    if amount <= 0:
        return redirect(url_for("wallet"))

    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        return "User not found", 404

    current_cash = Decimal(str(user.get("cash", "0")))
    new_cash = current_cash + amount

    users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"cash": str(new_cash)}}
    )

    return redirect(url_for("wallet"))


    
if __name__ == "__main__":
    app.run(debug=True)