from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app) # This tells your computer: "It's okay for my HTML file to talk to this script"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

@app.route('/get_stock_data')
def get_stock_data():
    ticker = request.args.get('ticker')
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=1y"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_fundamentals')
def get_fundamentals():
    ticker = request.args.get('ticker')
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}.NS?modules=summaryDetail,financialData,defaultKeyStatistics,assetProfile"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)