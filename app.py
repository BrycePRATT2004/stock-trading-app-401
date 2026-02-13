from decimal import Decimal
from flask import Flask, render_template

## Backend python logic




class Account:
##Purpose : Store financial state for user (cash and holding while 
##enforcing rules such as negative cash, cannot buy with insufficent funds, cannot sell stocks that you don't own etc

## Fields to be stored
# User-ID (Linking assets to user)
# Cash 
# Holdings 

# Methods
# - Deposit(amount) method
#buy(symbol, qty, price)
#- sell(symbol, qty, price)

# Validation rules inside buy/sell:
# - qty bought must be > 0
# - price must be > 0
# buy : cash >= qty*price
# sell: holdings[symbol] >= qty
# - Afteru updates : cash never <0, holdings never <0
    pass

    def __init__(self, cash):
        self.cash = Decimal(cash)

account = Account("10000.69") ##Placeholder starting balance
print(f"${account.cash:,.2f}") ## Data Formation for Cash IE $10,000.69 


class User:
## Purpose : A person who can login / own an account
## Fields to Store : - User-ID (int or string or uuid)
## - Username (str)
## - password_hash (string, not stored in plaintext)
    pass


class Trade:
## Purpose: Represents transactions (log entry)

#Fields to store:
# Trade ID, user id, , stock symbol, buy or sell, qty, price, timestamp
    pass


class GetPrices:
## returns stock prices for a symbol (can use fake/static prices first)

#Methods:
#-get_price(symbol) -> dec
# - validate symbol format
#return fake price 

#should not interface with accounts or trading
    pass


app = Flask(__name__)

@app.route("/")
def home():
    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True)