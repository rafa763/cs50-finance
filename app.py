import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    info = {}
    total = 0
    DATA = db.execute("SELECT symbol, name, SUM(shares) as owned FROM trx WHERE id = ? GROUP BY symbol HAVING owned > 0", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    # Input prices in the dictionary, symbol is the key
    for data in DATA:
        info[data["symbol"]] = lookup(data["symbol"])
        total += data["owned"] * info[data["symbol"]]["price"]
    return render_template("index.html", data=DATA, total=total, info=info, cash=cash[0]["cash"], )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # User reached route via POST
    if request.method == "POST":

        shares = request.form.get("shares")
        symbol = request.form.get("symbol")
        # Ensure symbol is provided
        if not symbol:
            return apology("Missing symbol", 400)

        # Ensure symbol is valid or exists
        response = lookup(symbol)
        if response == None:
            return apology("Invalid symbol", 400)

        # Ensure the shares are numeric
        if shares.isnumeric() != True:
            return apology("Invalid shares", 400)

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        bought = float(response["price"]) * float(request.form.get("shares"))

        # Ensure the user can afford the purchase
        if bought <= cash[0]["cash"]:

            # Insert the transaction in the database
            db.execute("INSERT INTO trx (name,symbol,shares,price, timestamp, id) VALUES(?,?,?,?,datetime('now'),?)", response["name"], response["symbol"], shares, response["price"], session["user_id"])
            # Update the user cash after the transaction is completed
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash[0]["cash"] - bought, session["user_id"])

            flash("Bought!")
            # Redirect the user to the home page after the purcahse is made
            return redirect("/")
        else:
            # Prompt user with apology if not enough cash
            return apology("can't afford", 400)

    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():

    DATA = db.execute("SELECT * FROM trx WHERE id = ?", session["user_id"])
    return render_template("history.html", data=DATA)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    # User reached route via POST
    if request.method == "POST":
        symbol = request.form.get("symbol")
        result = lookup(symbol)
        if result == None:
            return apology("Invalid symbol", 400)
        return render_template("quoted.html", name=result["name"], symbol=result["symbol"], price=result["price"])

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    # User reached route via POST
    if request.method == "POST":

        # Ensure username is submitted
        if not request.form.get("username"):
            return apology("Username is not available", 400)

        # Ensure password and confirmation are submitted
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Missing password", 400)

        # Ensure password and confirmation match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match", 400)

        # Ensure username is unique
        row = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(row) != 0:
            return apology("username already exists", 400)

        # # Ensure password length > 8
        # if len(request.form.get("password")) < 7:
        #     return apology("short password", 400)

        # # Ensure password contains numbers
        # if (request.form.get("password")).isalnum() == False:
        #     return apology("password must contain numbers", 400)

        # # Ensure password contains capitals
        # le = False
        # for letter in request.form.get("password"):
        #     if letter.isupper():
        #         le = True
        #         break
        # if le == False:
        #     return apology("password must contain capitals", 400)

        # Store the username and password hash in the databasse
        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", request.form.get("username"), generate_password_hash(request.form.get("password")))

        # Redirect user for login
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":

        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("Missing symbol", 400)

        # Ensure shares are provided
        if not request.form.get("shares"):
            return apology("Missing shares", 400)

        response = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))
        owned = db.execute("SELECT SUM(shares) as owned FROM trx WHERE id = ? and symbol = ?", session["user_id"], request.form.get("symbol"))
        sold = float(shares) * float(response["price"])

        # Eliminate overspending
        if shares <= owned[0]["owned"]:

            # Insert the transaction in the database
            db.execute("INSERT INTO trx (name,symbol,shares,price, timestamp, id) VALUES(?,?,-1 * ?,?,datetime('now'),?)", response["name"], response["symbol"], shares, response["price"], session["user_id"])
            # Update the user cash after the transaction is completed
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sold, session["user_id"])

            flash("Sold!")
            # Redirect the user to the home page after the purcahse is made
            return redirect("/")
        else:
            # Prompt user with apology if not enough cash
            return apology("too many shares", 400)

    else:
        symbols = db.execute("SELECT symbol, SUM(shares) as owned FROM trx WHERE id = ? GROUP BY symbol HAVING owned > 0", session["user_id"])
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
