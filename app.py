import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

def extract_ticker(text):
    # 1. Clean the text and convert to uppercase
    clean_text = re.sub(r'[^\w\s]', '', text).upper()
    words = clean_text.split()
    
    # 2. Hardcoded mapping for common Indian names
    mapping = {
        "SBI": "SBIN", "SBIN": "SBIN", "RELIANCE": "RELIANCE", 
        "TATA": "TATASTEEL", "HDFC": "HDFCBANK", "INFY": "INFY",
        "INFOSYS": "INFY", "ADANI": "ADANIENT", "ZOMATO": "ZOMATO"
    }
    
    # Check if any mapped word is in the sentence
    for word in words:
        if word in mapping:
            return mapping[word]
            
    # 3. If no mapping found, ignore common "filler" words and pick the most likely noun
    fillers = ["SHOULD", "I", "BUY", "INVEST", "IN", "ANALYZE", "KAISA", "HAI", "FOR", "THE", "STOCK", "SHARE"]
    potential_tickers = [w for w in words if w not in fillers]
    
    return potential_tickers[0] if potential_tickers else words[0]

@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
        data = request.json
        user_msg = data.get("message", "")
        
        # Use our smart extraction logic
        ticker = extract_ticker(user_msg)
        
        api_key = os.environ.get("GROQ_API_KEY")
        
        # Fetch Price
        price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=1d"
        r_price = requests.get(price_url, headers=HEADERS, timeout=10)
        price_data = r_price.json()

        if not price_data.get('chart', {}).get('result'):
            return jsonify({
                "ticker": ticker,
                "currentPrice": "N/A",
                "verdict": "WAIT",
                "reasoning": f"I couldn't identify the stock '{ticker}'. Try typing just the symbol like 'SBIN' or 'RELIANCE'.",
                "history": []
            }), 200

        current_price = price_data['chart']['result'][0]['meta']['regularMarketPrice']

        # Call Groq
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a professional NSE analyst. Provide a 3-sentence analysis in Hinglish. End with VERDICT: [BUY/HOLD/WAIT]."},
                {"role": "user", "content": f"Analyze {ticker} at ₹{current_price}. User message: {user_msg}"}
            ]
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        r_groq = requests.post(groq_url, json=payload, headers=headers, timeout=10)
        ai_resp = r_groq.json()['choices'][0]['message']['content']

        return jsonify({
            "ticker": ticker,
            "currentPrice": current_price,
            "verdict": "BUY" if "BUY" in ai_resp else "WAIT" if "WAIT" in ai_resp else "HOLD",
            "reasoning": ai_resp,
            "history": [{"year": 2025, "high": round(current_price*1.1), "low": round(current_price*0.9), "change": 10}]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
