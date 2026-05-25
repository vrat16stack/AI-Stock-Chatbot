// ChatbotPage.jsx
// Main chatbot page — shown after persona selection.
// Manages session memory, sends messages to FastAPI, renders responses.

import { useState, useRef, useEffect, useCallback } from "react";
import PersonaModal   from "./PersonaModal";
import ChatMessage    from "./ChatMessage";
import AnalysisCard   from "./AnalysisCard";
import TypingIndicator from "./TypingIndicator";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function ChatbotPage() {
  const [persona,   setPersona]   = useState(null);   // null = show modal
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [openCard,  setOpenCard]  = useState(null);   // analysis result for card

  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input after persona chosen
  useEffect(() => {
    if (persona) setTimeout(() => inputRef.current?.focus(), 100);
  }, [persona]);

  const handlePersonaSelect = (p) => {
    setPersona(p);
    const greeting = p === "investor"
      ? "Hi! I'm your personal stock advisor 📈\n\nTell me any NSE stock you're thinking about — I'll analyse it and give you a clear BUY / HOLD / SELL in simple language. You can also ask me anything about the market."
      : "Hey! I'm your NSE stock analyst 📊\n\nDrop any ticker or company name — I'll run full technical + fundamental + news analysis and give you a precise trade setup with entry, target, and stop loss. Ask me anything about the market too.";
    setMessages([{ role: "assistant", content: greeting, type: "general" }]);
  };

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg    = { role: "user", content: text, type: "user" };
    const newHistory = [...messages, userMsg];
    setMessages(newHistory);
    setInput("");
    setLoading(true);

    try {
      // Send last 12 messages as session history
      const history = newHistory
        .slice(-12)
        .filter(m => m.role === "user" || m.role === "assistant")
        .map(m => ({ role: m.role, content: m.content }));

      const res = await fetch(`${API_BASE}/chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ message: text, persona, history }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();

      const botMsg = {
        role:     "assistant",
        content:  data.message,
        type:     data.type,
        analysis: data.analysis || null,
        stock:    data.detected_stock || null,
        language: data.language || "en",
      };

      setMessages(prev => [...prev, botMsg]);

      // Auto-open analysis card
      if (data.type === "analysis" && data.analysis) {
        setOpenCard(data.analysis);
      }

    } catch (err) {
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: `Something went wrong: ${err.message}. Please try again.`,
        type:    "error",
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, messages, persona, loading]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Show persona modal on every load
  if (!persona) return <PersonaModal onSelect={handlePersonaSelect} />;

  const isInvestor  = persona === "investor";
  const accentColor = isInvestor ? "#16a34a" : "#0ea5e9";

  const quickPrompts = isInvestor
    ? ["Is HDFC Bank a good buy?", "Should I invest in Reliance?", "What is P/E ratio?", "Is Nifty overvalued?"]
    : ["Analyse RELIANCE", "TCS technical setup?", "HDFCBANK entry level?", "Explain Death Cross"];

  return (
    <div style={{
      minHeight:      "100vh",
      background:     "#0d1117",
      display:        "flex",
      flexDirection:  "column",
      fontFamily:     "'DM Sans','Segoe UI',system-ui,sans-serif",
    }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header style={{
        background:   "#161b22",
        borderBottom: "1px solid #21262d",
        padding:      "10px 20px",
        display:      "flex",
        alignItems:   "center",
        justifyContent:"space-between",
        position:     "sticky",
        top:          0,
        zIndex:       50,
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
          <div style={{
            width:36, height:36, borderRadius:"9px",
            background: isInvestor
              ? "linear-gradient(135deg,#16a34a,#15803d)"
              : "linear-gradient(135deg,#0ea5e9,#0284c7)",
            display:"flex", alignItems:"center",
            justifyContent:"center", fontSize:"17px",
          }}>📈</div>
          <div>
            <div style={{ color:"#e6edf3", fontSize:"14px", fontWeight:600 }}>
              NSE Stock AI
            </div>
            <div style={{ color:"#7d8590", fontSize:"11px" }}>
              Groq · NSE · Screener.in · Google News
            </div>
          </div>
        </div>

        <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
          <span style={{
            background: isInvestor ? "#16a34a22" : "#0ea5e922",
            border:     `1px solid ${isInvestor ? "#16a34a55" : "#0ea5e955"}`,
            color:      isInvestor ? "#4ade80" : "#38bdf8",
            fontSize:"11px", fontWeight:600,
            padding:"3px 10px", borderRadius:"20px",
          }}>
            {isInvestor ? "Investor" : "Trader"} mode
          </span>
          <button
            onClick={() => { setPersona(null); setMessages([]); setOpenCard(null); }}
            style={{
              background:"transparent",
              border:"1px solid #30363d",
              borderRadius:"6px",
              color:"#7d8590",
              fontSize:"11px",
              padding:"4px 10px",
              cursor:"pointer",
            }}
          >
            Switch
          </button>
        </div>
      </header>

      {/* ── Messages area ──────────────────────────────────────────────────── */}
      <div style={{ flex:1, overflowY:"auto", padding:"20px 16px 0" }}>
        <div style={{ maxWidth:"780px", margin:"0 auto" }}>

          {messages.map((msg, i) => (
            <ChatMessage
              key={i}
              message={msg}
              persona={persona}
              accentColor={accentColor}
              onViewAnalysis={(analysis) =>
                setOpenCard(openCard === analysis ? null : analysis)
              }
            />
          ))}

          {loading && <TypingIndicator accentColor={accentColor} />}

          {openCard && (
            <AnalysisCard
              data={openCard}
              persona={persona}
              accentColor={accentColor}
              onClose={() => setOpenCard(null)}
            />
          )}

          <div ref={bottomRef} style={{ height:"130px" }} />
        </div>
      </div>

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <div style={{
        position:    "sticky",
        bottom:      0,
        background:  "#0d1117",
        borderTop:   "1px solid #21262d",
        padding:     "12px 16px",
      }}>
        <div style={{ maxWidth:"780px", margin:"0 auto" }}>

          {/* Quick prompt chips */}
          <div style={{
            display:"flex", gap:"6px", flexWrap:"wrap", marginBottom:"10px",
          }}>
            {quickPrompts.map(p => (
              <button
                key={p}
                onClick={() => { setInput(p); inputRef.current?.focus(); }}
                style={{
                  background:   "#161b22",
                  border:       "1px solid #30363d",
                  borderRadius: "20px",
                  color:        "#7d8590",
                  fontSize:     "11px",
                  padding:      "4px 12px",
                  cursor:       "pointer",
                  whiteSpace:   "nowrap",
                  transition:   "all 0.15s",
                }}
                onMouseEnter={e => {
                  e.target.style.borderColor = accentColor;
                  e.target.style.color       = accentColor;
                }}
                onMouseLeave={e => {
                  e.target.style.borderColor = "#30363d";
                  e.target.style.color       = "#7d8590";
                }}
              >{p}</button>
            ))}
          </div>

          {/* Input row */}
          <div style={{
            display:      "flex",
            gap:          "8px",
            background:   "#161b22",
            border:       "1px solid #30363d",
            borderRadius: "12px",
            padding:      "6px 6px 6px 14px",
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isInvestor
                  ? "Ask about any NSE stock or market question..."
                  : "Enter stock ticker or ask anything about NSE markets..."
              }
              rows={1}
              style={{
                flex:        1,
                background:  "transparent",
                border:      "none",
                outline:     "none",
                color:       "#e6edf3",
                fontSize:    "14px",
                lineHeight:  "1.5",
                resize:      "none",
                padding:     "5px 0",
                fontFamily:  "inherit",
                maxHeight:   "100px",
                overflowY:   "auto",
              }}
              onInput={e => {
                e.target.style.height = "auto";
                e.target.style.height =
                  Math.min(e.target.scrollHeight, 100) + "px";
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || loading}
              style={{
                background: (!input.trim() || loading)
                  ? "#21262d"
                  : isInvestor
                    ? "linear-gradient(135deg,#16a34a,#15803d)"
                    : "linear-gradient(135deg,#0ea5e9,#0284c7)",
                border:        "none",
                borderRadius:  "8px",
                width:         "38px",
                height:        "38px",
                cursor:        (!input.trim() || loading)
                  ? "not-allowed" : "pointer",
                display:       "flex",
                alignItems:    "center",
                justifyContent:"center",
                fontSize:      "18px",
                flexShrink:    0,
                transition:    "all 0.15s",
                color:         (!input.trim() || loading) ? "#4d5566" : "#fff",
              }}
            >
              {loading ? "⏳" : "↑"}
            </button>
          </div>

          <div style={{
            color:"#4d5566", fontSize:"10px",
            textAlign:"center", marginTop:"6px",
          }}>
            AI analysis only — not SEBI registered financial advice
          </div>
        </div>
      </div>
    </div>
  );
}