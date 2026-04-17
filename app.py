import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}

def extract_ticker(text):
    clean = re.sub(r'[^\w\s]', '', text).upper()
    words = clean.split()
    mapping = {"SBI": "SBIN", "RELIANCE": "RELIANCE", "TATA": "TATASTEEL", "HDFC": "HDFCBANK", "INFY": "INFY"}
    for w in words:
        if w in mapping: return mapping[w]
    fillers = ["SHOULD", "I", "BUY", "INVEST", "IN", "ANALYZE", "KAISA", "HAI"]
    potential = [w for w in words if w not in fillers]
    return potential[0] if potential else words[0]

@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    if request.method == 'OPTIONS': return jsonify({"status": "ok"}), 200
    try:
        data = request.json
        user_msg = data.get("message", "")
        ticker = extract_ticker(user_msg)
        api_key = os.environ.get("GROQ_API_KEY")
        
        # Price Fetch
        price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=1d"
        price_data = requests.get(price_url, headers=HEADERS).json()
        if not price_data.get('chart', {}).get('result'):
            return jsonify({"error": f"Ticker {ticker} not found"}), 400
        current_price = price_data['chart']['result'][0]['meta']['regularMarketPrice']

        # Detailed Prompt
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a professional NSE India stock analyst. Give a VERY DETAILED, deep-dive analysis in Hinglish (Hindi + English). Discuss technicals, sentiment, and long-term outlook. You MUST provide a long response. End with VERDICT: [BUY/HOLD/WAIT]."},
                {"role": "user", "content": f"Analyze {ticker} at ₹{current_price}. Message: {user_msg}"}
            ]
        }
        r_groq = requests.post(groq_url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        ai_resp = r_groq.json()['choices'][0]['message']['content']

        return jsonify({"ticker": ticker, "currentPrice": current_price, "verdict": "BUY" if "BUY" in ai_resp else "WAIT" if "WAIT" in ai_resp else "HOLD", "reasoning": ai_resp})
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
