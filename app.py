#!/usr/bin/env python3
from flask import Flask
from flask import render_template, request, redirect, url_for
from algo import Algo
from config import STOCKS_FILE

app = Flask(__name__)

with open(STOCKS_FILE) as f:
    stocks = sorted(f.read().splitlines())


@app.route('/')
def index():
    return redirect(url_for('run'))


@app.route('/stocks', methods=['GET', 'POST'])
def stock():
    global stocks
    if request.method == 'POST':
        stocks = request.form["stocks"].splitlines()
        with open(STOCKS_FILE, "w+") as fi:
            fi.write("\n".join(stocks))
        return render_template("stocks.html", stocks="\n".join(stocks), success=True)
    return render_template("stocks.html", stocks="\n".join(stocks))


@app.route('/run', methods=['GET', 'POST'])
def run():
    result = []
    history = 10
    margin = 20
    last_close_margin = 5
    filter_by_last_close = True
    if request.method == 'POST':
        history = int(request.form["history"])
        margin = int(request.form["margin"])
        _stocks = request.form["stocks"].splitlines()
        filter_by_last_close = bool(request.form.getlist("filter-by-last-close"))
        last_close_margin = int(request.form["last-close-margin"])
        for sname in _stocks:
            try:
                result.extend(Algo(sname, history, margin, filter_by_last_close, last_close_margin).run_algo())
            except Exception as e:
                print(f"Error occured while running algo {e}")
                import traceback
                traceback.print_exc()
    else:
        global stocks
        _stocks = stocks

    return render_template("runAlgo.html", stocks="\n".join(_stocks), result=result or ["No results!"], history=history, margin=margin, last_close_margin=last_close_margin, filter_by_last_close=filter_by_last_close)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
