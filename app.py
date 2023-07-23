# in debug mode > flask --app app.py run --debug
import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/search")
def search():
    symbol = request.args.get("q")
    if symbol:
        price = lookup(symbol) #float by default
        query = str(price["price"]).split(".")
    else:
        query = ['-', '-']
    return query


@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    balance = rows[0]["cash"]
    username = rows[0]["username"]
    shares = db.execute("SELECT * FROM portfolio WHERE id = ?", session["user_id"])
    nwshares = []
    grndtotal = 0
    for share in shares:
        quantity = float(share['quantity'])
        total = float(share['price'])
        grndtotal += total 
        price = total/quantity
        nowprice = lookup(share['symbol'])['price']
        nwshares.append([share['symbol'], quantity, price, nowprice, total])

    return render_template("home.html", shares=nwshares, total=grndtotal, balance=balance, username=username)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    balance = rows[0]["cash"]
    idd = rows[0]["id"]

    if request.method == "POST":
        quantity = float(request.form.get("shares"))
        symbol = request.form.get("symbol").lower()
        price = lookup(symbol)
        if price:
            total = float(price["price"]) * quantity
            if balance >= total:
                datas = db.execute("SELECT * FROM portfolio WHERE symbol = ? AND id = ?", symbol, idd)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", balance - total, idd)
                
                if len(datas) == 1:
                    # already same stock in portfolio
                    db.execute("UPDATE portfolio SET quantity = ? WHERE symbol = ? AND id = ?", datas[0]["quantity"] + quantity, symbol, idd)

                    db.execute("UPDATE portfolio SET price = ? WHERE symbol = ? AND id = ?", datas[0]["price"] + total, symbol, idd)
                else:
                    db.execute("INSERT INTO portfolio (id, symbol, quantity, price) VALUES(?, ?, ?, ?)", idd, symbol, quantity, total)
                    
                flash(f'Bought {quantity} stock of {symbol}')
                return redirect("/")
            
            else:
                flash("You can't afford")
                return redirect("/buy")
        else:
            flash("Wrong symbol")
            return redirect("/buy")
    else:
        return render_template("buy.html", balance=balance)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    balance = rows[0]["cash"]
    idd = session["user_id"]
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))
        data = lookup(symbol)
        price = float(data["price"])
        total = price*shares

        portfolio = db.execute("SELECT * FROM portfolio WHERE id = ? AND symbol = ?", idd, symbol)
        quantity = portfolio[0]["quantity"]
        priceold = portfolio[0]["price"]

        if quantity > shares:
            db.execute("UPDATE portfolio SET quantity = ? WHERE symbol = ? AND id = ?", quantity-shares, symbol, idd)
            db.execute("UPDATE portfolio SET price = ? WHERE symbol = ? AND id = ?", priceold+total, symbol, idd)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", balance+total, idd)
            flash(f'Sold {shares} shares of {symbol}')
            return redirect("/")
        elif quantity == shares:
            db.execute("DELETE FROM portfolio WHERE symbol = ? AND id = ?", symbol, idd)
            db.execute("UPDATE portfolio SET price = ? WHERE symbol = ? AND id = ?", priceold+total, symbol, idd)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", balance+total, idd)
            flash(f'Sold {shares} shares of {symbol}')
            return redirect("/")
        else:
            flash("Not enough shares to sell")
            return redirect("/sell")
    else:
        symbols = db.execute("SELECT symbol FROM portfolio WHERE id = ?", idd)
        return render_template("sell.html", symbols=symbols, balance=balance)


@app.route("/admin")
@login_required
def admin():
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    balance = rows[0]["cash"]
    if session["user_id"] == 1:
        rows = db.execute("SELECT * FROM users")
        return render_template("admin.html", rows=rows, balance=balance)
    else:
        flash("You are not admin")
        return redirect("/")

@app.route("/admin/kick", methods=["GET", "POST"])
@login_required
def kick():
    if session["user_id"] == 1:
        id = request.form.get("id")
        if id:
            db.execute("DELETE FROM users WHERE id=?", id)
            db.execute("DELETE FROM portfolio WHERE id=?", id)
            flash(f'Kicked a user with id: {id}')
    return redirect("/")

@app.route("/admin/incre", methods=["GET", "POST"])
@login_required
def incre():
    if session["user_id"] == 1:
        id = request.form.get("id")
        to = request.form.get("to")
        if id and to:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", to, id)
            flash(f'Incremented cash of user with id: {id}')
    return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Must provide username")
            return redirect("/login")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Must provide password")
            return redirect("/login")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username and/or password")
            return redirect("/login")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash('Logged in successful')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    # Forget any user_id
    if not session.get("user_id"):
        return redirect("/login")
    else:
        session.clear()
        flash('Logged out successful')
        return redirect("/")

    # Redirect user to login form

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user. done"""
    session.clear()

    if request.method == "POST":
        usrname = request.form.get("username").strip()
        passw = request.form.get("password")
        repassw = request.form.get("repassword")

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Must provide username")
            return redirect("/register")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Must provide password")
            return redirect("/register")

        elif passw != repassw:
            flash("Must provide same password")
            return redirect("/register")

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) == 1:
            flash("Username already taken")
            return redirect("/register")
        else:
            db.execute("INSERT INTO users (username, hash, cash) VALUES(?, ?, ?)", usrname, generate_password_hash(passw), 100.00)
            flash('Registered successfully')
            session["user_id"] = usrname
            return redirect("/")

    else:
        return render_template("register.html")













