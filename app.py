import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

# 1. New Route for the Chatbot UI
@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    user_msg = data.get("message", "").upper()
    
    # Extract ticker (Simple logic: first word or word before 'KAISA')
    ticker = user_msg.split()[0] 
    if "SBI" in user_msg: ticker = "SBIN"
    
    # Get Groq Key from Render Secrets
    api_key = os.environ.get("GROQ_API_KEY")
    
    try:
        # Fetch actual price for the AI to use
        price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=1d"
        price_data = requests.get(price_url, headers=HEADERS).json()
        current_price = price_data['chart']['result'][0]['meta']['regularMarketPrice']

        # Call Groq
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a top NSE India analyst. Provide a brief analysis with VERDICT: [BUY/HOLD/WAIT]."},
                {"role": "user", "content": f"Analyze {ticker} current price ₹{current_price}. Question: {user_msg}"}
            ]
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        r = requests.post(groq_url, json=payload, headers=headers)
        ai_resp = r.json()['choices'][0]['message']['content']

        # Prepare dummy history for the table UI
        history = [
            {"year": 2024, "high": round(current_price*1.1), "low": round(current_price*0.9), "change": 10},
            {"year": 2025, "high": round(current_price*1.2), "low": round(current_price*1.0), "change": 12}
        ]

        return jsonify({
            "ticker": ticker,
            "currentPrice": current_price,
            "verdict": "BUY" if "BUY" in ai_resp else "WAIT" if "WAIT" in ai_resp else "HOLD",
            "reasoning": ai_resp,
            "history": history
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Keep your original routes for debugging
@app.route('/get_stock_data')
def get_stock_data():
    ticker = request.args.get('ticker')
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=1y"
    r = requests.get(url, headers=HEADERS)
    return jsonify(r.json())

if __name__ == '__main__':
    # CRITICAL: Render needs this port logic
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
