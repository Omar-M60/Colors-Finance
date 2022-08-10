import os

from flask_sqlalchemy import SQLAlchemy
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configuring the database using flask-sqlalchemy and automap for linking the database with the flask app
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Initializing the users Table
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    username = db.Column(db.Text, nullable=False, unique=True)
    hash = db.Column(db.Text, nullable=False)
    cash = db.Column(db.Numeric, nullable=False, default=10000)

    stocks = db.relationship('Stocks', backref='user')
    transactions = db.relationship('Transactions', backref='user')

# Initializing the relationshinal table
stocks_trans = db.Table ( 'stocks_trans',
    db.Column("stock_id", db.Integer, db.ForeignKey("stocks.id"), primary_key=True),
    db.Column("trans_id", db.Integer, db.ForeignKey("transactions.id"), primary_key=True),

    db.PrimaryKeyConstraint("stock_id", "trans_id")
)

# Initializing the stocks Table
class Stocks(db.Model):
    __tablename__ = "stocks"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    stock = db.Column(db.Text, nullable=False)
    total_shares = db.Column(db.Integer, nullable=False, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    trans = db.relationship("Transactions", secondary=stocks_trans)

# Initializing the transactions Table
class Transactions(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    status = db.Column(db.String(4), nullable=False)
    shares = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now())

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# create all tables mentioned above
db.create_all()

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # initializing lists to be able to display the price, stock name and total holding value of each stock 
    prices = []
    holdings = []
    stock_names = []

    # considering by default that the user has stocks
    hasStock = True

    # taking the user id
    user_id = session["user_id"]

    # quering for the user depending on the user id
    user = Users.query.filter(Users.id == user_id).scalar()

    # adding the amount of cash the user have to the total value of balance + holding stocks
    total_holdings_value = float(user.cash)

    # getting all the stocks owned by the user
    stocks = Stocks.query.filter(Users.id == user_id).all()

    # check if the user has stocks
    if not len(stocks) >= 1:
        hasStock = False

    # itirating over each stock in the list of stocks owned by the user
    for stock in stocks:
        # looking up for the stock using the lookup function
        stock_status  = lookup(stock.stock)

        # getting the price of the stock
        price = stock_status["price"]

        # adding that price to the list of prices
        prices.append(price)

        # getting the name of the stock
        name = stock_status["name"]

        # adding the name to the list of stock names
        stock_names.append(name)

        # adding to the list of holdings the total holding of the stock which is the price of the stock times the shares owned
        holdings.append(price * stock.total_shares)

    # itirating over each holding of every stock owned by the user and adding it to the total value of all holdings
    for holding in holdings:
        total_holdings_value += float(holding)


    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("index.html", balance=user.cash, hasStock=hasStock, stocks=stocks, stock_names=stock_names, prices=prices, holdings=holdings, total_holdings_value=total_holdings_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # gets the symbol entered by user
        symbol = request.form.get("symbol")

        # checking if the number of shares is left empty, returning an apology to avoid future error
        if not request.form.get("shares"):
            return apology("Missing Number of Shares you dumbass, How in the bloody sock I will know how many times you wanna buy")

        # getting number of shares entered by user and convert it to integer
        shares = int(request.form.get("shares"))

        # calling lookup function on the symbol desired by the user
        symbol_stat = lookup(symbol)

        # checks if the symbol exists, returning an apology in case it doesn't
        if not symbol_stat:
            return apology("Ain't no symbol like dat", 403)

        # checks if the number of shares is equal to 0 or negative number, returning an apology in case it is
        if shares <= 0:
            return apology(f"Number of shares cannot be 0 or a negative number! How the FUCK can you buy 0 shares or  {shares} shares!", 403)

        # storing user_id, user query and price of the stock times the number of shares
        user_id = session["user_id"]
        user = Users.query.filter(Users.id == user_id).scalar()
        price = symbol_stat["price"] * shares

        # check if the user has enough cash to afford the purchase
        if price > user.cash:
            return apology("You are Broke, HAHA!", 403)

        # adding the transaction to the database
        transaction = Transactions(status="buy", shares=shares, price=price, user_id=user_id)
        db.session.add(transaction)

        # selecting from the Stocks table the row where the user id and stock symbol are
        stock = Stocks.query.filter(Stocks.user_id == user_id, Stocks.stock == symbol_stat["symbol"]).scalar()

        # if the symbol doesn't already exists in the table add it to the database
        if not stock:
            new_stock = Stocks(stock=symbol_stat["symbol"], total_shares=shares, user_id=user_id)
            db.session.add(new_stock)

        # if it already exists, just update the total number of shares
        else:
            stock.total_shares += shares
        
        # update the user's cash balance
        user.cash = float(user.cash) - float(price)

        # commiting all the changes above to the database
        db.session.commit()

        # redirecting the buy form
        return redirect("/buy")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    stocks = db.session.query(Stocks).join(stocks_trans).join(Transactions).filter(Transactions.user_id == session["user_id"]).all()
    transactions = Transactions.query.filter(Transactions.user_id == session["user_id"]).all()

    for stock in stocks:
        print(stock.stock)

    return render_template("history.html", transactions=transactions, stocks=stocks)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username, how the bloody bag of shiz I should know who are you!!", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password how the bloody bucket I should know it is you", 403)

        # Query database for username
        result = Users.query.filter(Users.username == request.form.get("username")).scalar()
        

        # Ensure username exists and password is correct
        if not bool(result) or not check_password_hash(result.hash, request.form.get("password")):
            return apology("invalid username and/or password, you guess puta haha", 403)
            
        # Remember which user has logged in
        session["user_id"] = result.id

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
    """Get stock quote."""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # storing the symbol entered in a variable called symbol
        symbol = request.form.get("symbol")

        # using the lookup function we search for the symbol
        symbol_stat = lookup(symbol)

        # if the lookup has failed (is none) then apology that the symbol does not exist
        if not symbol_stat:
            return apology("Ain't no symbol like dat", 403)

        # if the search was successful load the quoted page where the name, price, symbol is displayed
        return render_template("quoted.html", name=symbol_stat["name"], price=symbol_stat["price"], symbol=symbol_stat["symbol"])

    # if get then load the quote page to request a symbol from the user
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # getting the username typped in
        username = request.form.get("username")
        
        # make sure the username is not blank, return apology otherwise
        if not username:
            return apology("Username! stupid", 403)

        # getting all the usernames from the database, it returns a list of tuples
        usernames = Users.query.with_entities(Users.username).all()
        
        # checking if the username already exist in the database
        for name in usernames:
            if username == name[0]:
                return apology("Username already taken! son of a biscuit >:(", 403)

        # checking if the user entered a password
        if not request.form.get("password"):
            return apology("Must provide password Stupidoo!", 403)

        # checking if the password match the confirm password typped in, return apology if not
        if  request.form.get("password") != request.form.get("confirm-password"):
            return apology("Password must match the confirmation password! What do you think confirm password stand for dumbass!", 403)

        # inserting the user in the database, hashing the password using generate_password_hash function then commiting it
        user = Users(username=username, hash=generate_password_hash(request.form.get("password")))
        db.session.add(user)
        db.session.commit()
        
        # remember who registered
        session["user_id"] = user.id
        
        # return to the homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # gets the symbol entered by user
        symbol = request.form.get("symbol")

        # checking if the number of shares is left empty, returning an apology to avoid future error
        if not request.form.get("shares"):
            return apology("Missing Number of Shares you dumbass, How in the bloody sock I will know how many shares you wanna sell")

        # getting number of shares entered by user and convert it to integer
        shares = int(request.form.get("shares"))

        # calling lookup function on the symbol desired by the user
        symbol_stat = lookup(symbol)

        # checks if the symbol exists, returning an apology in case it doesn't
        if not symbol_stat:
            return apology("Ain't no symbol like dat", 403)

        # checks if the number of shares is equal to 0 or negative number, returning an apology in case it is
        if shares <= 0:
            return apology(f"Number of shares cannot be 0 or a negative number! How the FUCK can you sell 0 shares or  {shares} shares!", 403)

        # storing the user id, and the user info into variables
        user_id = session["user_id"]
        user = Users.query.filter(Users.id == user_id).scalar()

        # getting all the stocks owned by the user
        stocks = Stocks.query.filter(Stocks.user_id == user_id).all()

        # checking if the stock submited is owned by the user
        for stock in stocks:
            if symbol_stat["symbol"] == stock.stock:

                # checking if the user has enough shares to sell
                if shares > stock.total_shares:
                    return apology("You do not own that many shares you puta!")

                # storing the total price of the number of shares times the price of one share
                price = symbol_stat["price"] * shares

                # adding the transaction to the database
                transaction = Transactions(status="sell", shares=shares, price=price, user_id=user_id)
                db.session.add(transaction)

                # if the number of shares entered is equal to the number of shares owned then delete the stock from the database, since the user doesn't own the stock anymore
                if shares == stock.total_shares:
                    db.session.delete(stock)

                # else if the number of shares entered is less then the shares owned, just decrease the number of shares
                else:
                    stock.total_shares -= shares

                # update the user's cash balance
                user.cash = float(user.cash) + float(price)

                # commiting all the changes above to the database
                db.session.commit()

                # redirecting the buy form
                return redirect("/sell")

            # continue checking if the symbol entered doesnt match this stock
            else:
                continue

        # return an apology in case the user doesn't own the stock
        return apology("You don't own the stock you dumbass!!!!", 403)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")