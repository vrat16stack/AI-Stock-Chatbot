// AnalysisCard.jsx
// Expandable full-detail analysis card shown below the chat bubble.
// Three tabs: Technical | Fundamental | News & Market
// Adapts depth based on persona (trader = full tables, investor = simplified).

import { useState } from "react";

export default function AnalysisCard({ data, persona, accentColor, onClose }) {
  const [tab, setTab] = useState("technical");
  const isInvestor   = persona === "investor";

  const v        = data.verdict || {};
  const p        = data.price   || {};
  const decision = v.decision   || "HOLD";

  const VS = {
    BUY:  { bg:"#0d2818", border:"#16a34a", text:"#4ade80" },
    HOLD: { bg:"#2a1f00", border:"#ca8a04", text:"#fbbf24" },
    SELL: { bg:"#2a0a0a", border:"#dc2626", text:"#f87171" },
  };
  const vs = VS[decision] || VS.HOLD;

  const fmt = (x, fallback="N/A") => {
    if (x == null || x === 0 || x === "") return fallback;
    return typeof x === "number"
      ? `₹${x.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
      : x;
  };

  return (
    <div style={{
      background:    "#161b22",
      border:        `1px solid ${vs.border}44`,
      borderRadius:  "14px",
      marginBottom:  "20px",
      overflow:      "hidden",
    }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        background:   vs.bg,
        borderBottom: `1px solid ${vs.border}33`,
        padding:      "16px 20px",
        display:      "flex",
        justifyContent:"space-between",
        alignItems:   "flex-start",
        flexWrap:     "wrap",
        gap:          "12px",
      }}>
        <div>
          <div style={{
            display:      "inline-flex",
            alignItems:   "center",
            gap:          "8px",
            background:   vs.border + "22",
            border:       `1px solid ${vs.border}66`,
            borderRadius: "8px",
            padding:      "4px 14px",
            marginBottom: "8px",
          }}>
            <span style={{ color:vs.text, fontSize:"17px", fontWeight:700 }}>
              {decision === "BUY" ? "🟢"
               : decision === "SELL" ? "🔴" : "🟡"} {decision}
            </span>
            <span style={{ color:vs.text+"99", fontSize:"12px" }}>
              {v.confidence} confidence
            </span>
          </div>
          <div style={{ color:"#e6edf3", fontSize:"16px", fontWeight:600 }}>
            {data.display_name}
            <span style={{ color:"#7d8590", fontSize:"13px",
                           fontWeight:400, marginLeft:"8px" }}>
              {data.symbol}
            </span>
          </div>
          <div style={{ color:"#7d8590", fontSize:"12px", marginTop:"2px" }}>
            {p.sector} · {v.cap_category}
          </div>
        </div>

        <div style={{ textAlign:"right" }}>
          <div style={{ color:"#e6edf3", fontSize:"22px", fontWeight:700 }}>
            ₹{(p.current || 0).toLocaleString("en-IN",
              { maximumFractionDigits:2 })}
          </div>
          <div style={{
            color:    (p.change_pct || 0) >= 0 ? "#4ade80" : "#f87171",
            fontSize: "12px",
          }}>
            {(p.change_pct || 0) >= 0 ? "▲" : "▼"}{" "}
            {Math.abs(p.change_pct || 0).toFixed(2)}%
          </div>
          <div style={{ color:"#7d8590", fontSize:"11px", marginTop:"2px" }}>
            {p.label}
          </div>
        </div>
      </div>

      {/* ── Key numbers strip ───────────────────────────────────────────────── */}
      <div style={{
        display:             "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(120px,1fr))",
        gap:                 "1px",
        background:          "#21262d",
        borderBottom:        "1px solid #21262d",
      }}>
        {[
          { label:"Target",
            value: v.target_price
              ? `₹${v.target_price.toLocaleString("en-IN",{maximumFractionDigits:0})}`
              : "—",
            sub:   v.upside_pct ? `+${v.upside_pct}% upside` : "",
            color: "#4ade80" },
          { label:"Stop Loss",
            value: v.stop_loss
              ? `₹${v.stop_loss.toLocaleString("en-IN",{maximumFractionDigits:0})}`
              : "—",
            sub: "", color:"#f87171" },
          { label: decision === "HOLD" ? "Entry Level" : "Current Entry",
            value: v.entry_level
              ? `₹${v.entry_level.toLocaleString("en-IN",{maximumFractionDigits:0})}`
              : "Now",
            sub: "", color:"#fbbf24" },
          { label:"Risk : Reward",
            value: v.risk_reward ? `1 : ${v.risk_reward}` : "—",
            sub: "", color: accentColor },
        ].map(item => (
          <div key={item.label} style={{
            background:"#161b22", padding:"11px 14px",
          }}>
            <div style={{ color:"#7d8590", fontSize:"11px",
                          marginBottom:"3px" }}>
              {item.label}
            </div>
            <div style={{ color:item.color, fontSize:"15px",
                          fontWeight:600 }}>
              {item.value}
            </div>
            {item.sub && (
              <div style={{ color:"#4d5566", fontSize:"11px" }}>
                {item.sub}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Entry reason (HOLD only) ────────────────────────────────────────── */}
      {decision === "HOLD" && v.entry_reason && (
        <div style={{
          background:   "#2a1f00",
          borderBottom: "1px solid #ca8a0422",
          padding:      "10px 20px",
          color:        "#d97706",
          fontSize:     "13px",
        }}>
          📍 <strong>Why this entry:</strong> {v.entry_reason}
        </div>
      )}

      {/* ── AI summary ──────────────────────────────────────────────────────── */}
      <div style={{
        padding:      "14px 20px",
        borderBottom: "1px solid #21262d",
      }}>
        <div style={{ color:"#7d8590", fontSize:"11px",
                      letterSpacing:"0.05em", textTransform:"uppercase",
                      marginBottom:"6px" }}>
          AI Analysis
        </div>
        <div style={{ color:"#c9d1d9", fontSize:"13px", lineHeight:"1.75" }}>
          {v.detail}
        </div>
        {v.risk_factors && (
          <div style={{ marginTop:"8px", color:"#f87171", fontSize:"12px" }}>
            ⚠️ <strong>Risks:</strong> {v.risk_factors}
          </div>
        )}
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div style={{
        display:      "flex",
        background:   "#0d1117",
        borderBottom: "1px solid #21262d",
      }}>
        {[
          { id:"technical",   label:"📊 Technical"      },
          { id:"fundamental", label:"🏢 Fundamental"    },
          { id:"news",        label:"📰 News & Market"  },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              flex:         1,
              padding:      "11px 6px",
              background:   "transparent",
              border:       "none",
              borderBottom: tab === t.id
                ? `2px solid ${accentColor}`
                : "2px solid transparent",
              color:        tab === t.id ? accentColor : "#7d8590",
              fontSize:     "12px",
              fontWeight:   tab === t.id ? 600 : 400,
              cursor:       "pointer",
              transition:   "all 0.15s",
              fontFamily:   "inherit",
            }}
          >{t.label}</button>
        ))}
      </div>

      {/* ── Tab content ─────────────────────────────────────────────────────── */}
      <div style={{ padding:"16px 20px" }}>
        {tab === "technical"   &&
          <TechTab   data={data} isInvestor={isInvestor} accent={accentColor} />}
        {tab === "fundamental" &&
          <FundTab   data={data} isInvestor={isInvestor} accent={accentColor} />}
        {tab === "news"        &&
          <NewsTab   data={data} accent={accentColor} />}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
      <div style={{
        borderTop:  "1px solid #21262d",
        padding:    "10px 20px",
        display:    "flex",
        justifyContent:"space-between",
        alignItems: "center",
      }}>
        <span style={{ color:"#4d5566", fontSize:"11px" }}>
          NSE API · Screener.in · Google News · Groq AI
        </span>
        <button
          onClick={onClose}
          style={{
            background:"transparent",
            border:"1px solid #30363d",
            borderRadius:"6px",
            color:"#7d8590",
            fontSize:"11px",
            padding:"4px 12px",
            cursor:"pointer",
            fontFamily:"inherit",
          }}
        >Close</button>
      </div>
    </div>
  );
}


// ── Technical Tab ─────────────────────────────────────────────────────────────

function TechTab({ data, isInvestor, accent }) {
  const t = data.technical || {};

  const sigColor = s =>
    s === "BULLISH" ? "#4ade80"
    : s === "BEARISH" ? "#f87171"
    : "#fbbf24";

  if (isInvestor) {
    return (
      <div>
        <Label>Chart Summary</Label>
        <div style={{
          background:   "#0d1117",
          borderRadius: "8px",
          padding:      "14px",
          color:        "#c9d1d9",
          fontSize:     "13px",
          lineHeight:   "1.75",
          marginBottom: "16px",
        }}>
          {t.investor_summary || "Technical summary not available."}
        </div>
        <div style={{
          display:"grid",
          gridTemplateColumns:"1fr 1fr",
          gap:"10px",
          marginBottom:"16px",
        }}>
          <StatBox label="Overall signal"
            value={t.signal} color={sigColor(t.signal)} />
          <StatBox label="Bull score"
            value={`${t.bull_pct}%`} color={accent} />
          <StatBox label="Candles analysed"
            value={`${t.candles} days`} color="#7d8590" />
          <StatBox label="Cap category"
            value={data.verdict?.cap_category || "N/A"} color="#7d8590" />
        </div>

        {t.support?.length > 0 && (
          <>
            <Label>Support levels (good entry zones)</Label>
            <div style={{ display:"flex", gap:"8px", flexWrap:"wrap",
                          marginBottom:"12px" }}>
              {t.support.map(s => (
                <PricePill key={s} price={s} color="#4ade80" tag="S" />
              ))}
            </div>
          </>
        )}
        {t.resistance?.length > 0 && (
          <>
            <Label>Resistance levels</Label>
            <div style={{ display:"flex", gap:"8px", flexWrap:"wrap" }}>
              {t.resistance.map(r => (
                <PricePill key={r} price={r} color="#f87171" tag="R" />
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  // Trader — full table
  return (
    <div>
      <Label>Indicator breakdown</Label>
      <div style={{ overflowX:"auto" }}>
        <table style={{ width:"100%", borderCollapse:"collapse",
                        fontSize:"12px" }}>
          <thead>
            <tr style={{ color:"#7d8590" }}>
              {["Indicator","Value","Signal","Interpretation"].map(h => (
                <th key={h} style={{
                  padding:"6px 10px",
                  textAlign: h === "Interpretation" ? "left" : "center",
                  fontSize:"10px",
                  fontWeight:600,
                  letterSpacing:"0.05em",
                  textTransform:"uppercase",
                  borderBottom:"1px solid #21262d",
                  whiteSpace:"nowrap",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(t.table || []).map((row, i) => (
              <tr key={i} style={{
                borderTop: "1px solid #21262d",
                background: i === (t.table?.length||1)-1
                  ? "#0d111766" : "transparent",
              }}>
                <td style={{ padding:"9px 10px", color:"#c9d1d9",
                             fontWeight: i===(t.table?.length||1)-1 ? 600 : 400,
                             whiteSpace:"nowrap" }}>
                  {row.indicator}
                </td>
                <td style={{ padding:"9px 10px", color:"#7d8590",
                             fontFamily:"monospace", fontSize:"11px",
                             textAlign:"center" }}>
                  {row.value}
                </td>
                <td style={{ padding:"9px 10px", textAlign:"center" }}>
                  <SigBadge signal={row.signal} />
                </td>
                <td style={{ padding:"9px 10px", color:"#8b949e",
                             textAlign:"left" }}>
                  {row.interpretation}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr",
                    gap:"12px", marginTop:"16px" }}>
        <div>
          <Label>Support</Label>
          <div style={{ display:"flex", gap:"6px", flexWrap:"wrap" }}>
            {t.support?.length > 0
              ? t.support.map(s =>
                  <PricePill key={s} price={s} color="#4ade80" tag="S" />)
              : <Dim>N/A</Dim>}
          </div>
        </div>
        <div>
          <Label>Resistance</Label>
          <div style={{ display:"flex", gap:"6px", flexWrap:"wrap" }}>
            {t.resistance?.length > 0
              ? t.resistance.map(r =>
                  <PricePill key={r} price={r} color="#f87171" tag="R" />)
              : <Dim>N/A</Dim>}
          </div>
        </div>
      </div>

      {t.insufficient?.length > 0 && (
        <div style={{ marginTop:"10px", color:"#7d8590", fontSize:"11px" }}>
          ℹ️ Skipped (insufficient data): {t.insufficient.join(", ")}
        </div>
      )}
    </div>
  );
}


// ── Fundamental Tab ───────────────────────────────────────────────────────────

function FundTab({ data, isInvestor, accent }) {
  const f = data.fundamental || {};

  return (
    <div>
      {/* Score bar */}
      <div style={{ marginBottom:"16px" }}>
        <div style={{ display:"flex", justifyContent:"space-between",
                      marginBottom:"6px" }}>
          <Label>Fundamental score</Label>
          <span style={{ color:accent, fontSize:"13px", fontWeight:600 }}>
            {f.score}/100
          </span>
        </div>
        <div style={{ height:"6px", background:"#21262d",
                      borderRadius:"3px" }}>
          <div style={{
            height:       "100%",
            borderRadius: "3px",
            width:        `${f.score}%`,
            background:   (f.score||0) >= 60 ? "#16a34a"
                          : (f.score||0) >= 35 ? "#ca8a04"
                          : "#dc2626",
            transition:   "width 0.6s ease",
          }} />
        </div>
      </div>

      {f.pe_flag && (
        <div style={{
          background:   "#2a1f00",
          border:       "1px solid #ca8a0444",
          borderRadius: "8px",
          padding:      "10px 14px",
          color:        "#fbbf24",
          fontSize:     "12px",
          marginBottom: "14px",
        }}>
          ⚠️ {f.pe_flag}
        </div>
      )}

      {isInvestor ? (
        <>
          <Label>Company health at a glance</Label>
          <div style={{ display:"flex", flexDirection:"column",
                        gap:"6px", marginBottom:"14px" }}>
            {(f.table || []).map((row, i) => (
              <div key={i} style={{
                display:        "flex",
                justifyContent: "space-between",
                alignItems:     "center",
                background:     "#0d1117",
                borderRadius:   "8px",
                padding:        "10px 14px",
              }}>
                <div>
                  <div style={{ color:"#c9d1d9", fontSize:"13px" }}>
                    {row.metric}
                  </div>
                  <div style={{ color:"#7d8590", fontSize:"11px" }}>
                    {row.plain}
                  </div>
                </div>
                <div style={{ textAlign:"right" }}>
                  <div style={{ color:"#e6edf3", fontSize:"13px",
                                fontWeight:500 }}>
                    {row.value}
                  </div>
                  <VerdictChip v={row.verdict} />
                </div>
              </div>
            ))}
          </div>
          <div style={{
            background:   "#0d1117",
            borderRadius: "8px",
            padding:      "12px 14px",
            color:        "#c9d1d9",
            fontSize:     "13px",
            lineHeight:   "1.75",
          }}>
            {f.investor_summary}
          </div>
        </>
      ) : (
        <>
          <Label>Full fundamental breakdown</Label>
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", borderCollapse:"collapse",
                            fontSize:"12px" }}>
              <thead>
                <tr style={{ color:"#7d8590" }}>
                  {["Metric","Value","Verdict"].map(h => (
                    <th key={h} style={{
                      padding:"6px 10px",
                      textAlign: h === "Metric" ? "left" : "center",
                      fontSize:"10px",
                      fontWeight:600,
                      letterSpacing:"0.05em",
                      textTransform:"uppercase",
                      borderBottom:"1px solid #21262d",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(f.table || []).map((row, i) => (
                  <tr key={i} style={{ borderTop:"1px solid #21262d" }}>
                    <td style={{ padding:"9px 10px", color:"#c9d1d9",
                                 textAlign:"left" }}>
                      {row.metric}
                    </td>
                    <td style={{ padding:"9px 10px", color:"#7d8590",
                                 fontFamily:"monospace", fontSize:"11px",
                                 textAlign:"center" }}>
                      {row.value}
                    </td>
                    <td style={{ padding:"9px 10px", textAlign:"center" }}>
                      <VerdictChip v={row.verdict} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {f.target_basis && (
            <div style={{ marginTop:"12px", color:"#7d8590",
                          fontSize:"11px" }}>
              📊 Target based on: {f.target_basis}
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ── News Tab ──────────────────────────────────────────────────────────────────

function NewsTab({ data, accent }) {
  const n = data.news    || {};
  const m = data.market  || {};

  const sentColor = s =>
    s === "POSITIVE" ? "#4ade80"
    : s === "NEGATIVE" ? "#f87171"
    : "#fbbf24";

  const fgColor = score =>
    score <= 25 ? "#f87171"
    : score <= 45 ? "#fb923c"
    : score <= 55 ? "#fbbf24"
    : score <= 75 ? "#86efac"
    : "#4ade80";

  return (
    <div>
      {/* Sentiment + market cards */}
      <div style={{
        display:             "grid",
        gridTemplateColumns: "repeat(auto-fit,minmax(110px,1fr))",
        gap:                 "8px",
        marginBottom:        "16px",
      }}>
        <StatBox label="News sentiment"
          value={n.sentiment} color={sentColor(n.sentiment)} />
        <StatBox label="AI sentiment"
          value={n.overall}   color={sentColor(n.overall)} />
        <StatBox label="Nifty 50"
          value={m.nifty50
            ? `₹${m.nifty50.toLocaleString("en-IN",{maximumFractionDigits:0})}`
            : "N/A"}
          color={accent} />
        <StatBox
          label="Fear & Greed"
          value={`${m.fear_greed_score} — ${m.fear_greed_rating} ${m.fear_greed_emoji||""}`}
          color={fgColor(m.fear_greed_score||50)} />
      </div>

      {m.fear_greed_advice && (
        <div style={{
          background:   "#0d1117",
          borderRadius: "8px",
          padding:      "10px 14px",
          color:        "#c9d1d9",
          fontSize:     "12px",
          lineHeight:   "1.6",
          marginBottom: "16px",
        }}>
          💡 {m.fear_greed_advice}
        </div>
      )}

      {n.company_headlines?.length > 0 && (
        <>
          <Label>Company news</Label>
          <div style={{ display:"flex", flexDirection:"column",
                        gap:"6px", marginBottom:"14px" }}>
            {n.company_headlines.map((h, i) => (
              <div key={i} style={{
                background:   "#0d1117",
                borderRadius: "8px",
                padding:      "10px 14px",
                color:        "#c9d1d9",
                fontSize:     "12px",
                lineHeight:   "1.5",
                borderLeft:   `3px solid ${accent}66`,
              }}>
                {h}
              </div>
            ))}
          </div>
        </>
      )}

      {n.macro_headlines?.length > 0 && (
        <>
          <Label>India market news</Label>
          <div style={{ display:"flex", flexDirection:"column", gap:"6px" }}>
            {n.macro_headlines.map((h, i) => (
              <div key={i} style={{
                background:   "#0d1117",
                borderRadius: "8px",
                padding:      "10px 14px",
                color:        "#8b949e",
                fontSize:     "12px",
                lineHeight:   "1.5",
                borderLeft:   "3px solid #30363d",
              }}>
                {h}
              </div>
            ))}
          </div>
        </>
      )}

      {(n.total_articles || 0) === 0 && (
        <div style={{ color:"#4d5566", fontSize:"13px",
                      textAlign:"center", padding:"20px" }}>
          No recent news found for this stock.
        </div>
      )}
    </div>
  );
}


// ── Shared sub-components ─────────────────────────────────────────────────────

function Label({ children }) {
  return (
    <div style={{
      color:         "#7d8590",
      fontSize:      "11px",
      fontWeight:    600,
      letterSpacing: "0.05em",
      textTransform: "uppercase",
      marginBottom:  "8px",
    }}>
      {children}
    </div>
  );
}

function StatBox({ label, value, color }) {
  return (
    <div style={{ background:"#0d1117", borderRadius:"8px",
                  padding:"10px 12px" }}>
      <div style={{ color:"#7d8590", fontSize:"11px",
                    marginBottom:"3px" }}>{label}</div>
      <div style={{ color: color || "#e6edf3", fontSize:"13px",
                    fontWeight:600 }}>{value}</div>
    </div>
  );
}

function PricePill({ price, color, tag }) {
  return (
    <div style={{
      background:   color + "22",
      border:       `1px solid ${color}44`,
      borderRadius: "6px",
      padding:      "4px 10px",
      color:        color,
      fontSize:     "12px",
      fontWeight:   500,
    }}>
      {tag} ₹{Number(price).toLocaleString("en-IN")}
    </div>
  );
}

function SigBadge({ signal }) {
  const map = {
    BULLISH: { bg:"#0d2818", color:"#4ade80", border:"#16a34a44" },
    BEARISH: { bg:"#2a0a0a", color:"#f87171", border:"#dc262644" },
    NEUTRAL: { bg:"#2a1f00", color:"#fbbf24", border:"#ca8a0444" },
    "N/A":   { bg:"#1a1a1a", color:"#4d5566", border:"#30363d44" },
  };
  const s = map[signal] || map["N/A"];
  return (
    <span style={{
      background:   s.bg,
      border:       `1px solid ${s.border}`,
      borderRadius: "4px",
      padding:      "2px 8px",
      color:        s.color,
      fontSize:     "10px",
      fontWeight:   600,
      display:      "inline-block",
    }}>
      {signal}
    </span>
  );
}

function VerdictChip({ v }) {
  if (!v) return null;
  const pos = ["Strong","High","Low debt","Growing","Yes","Efficient",
               "Undervalued","Good","Institutional support",
               "Positive","Income stock"].some(x => v.includes(x));
  const neg = ["Weak","Declining","High debt","Negative",
               "Overvalued","WARNING"].some(x => v.includes(x));
  const color = pos ? "#4ade80" : neg ? "#f87171" : "#fbbf24";
  return <span style={{ color, fontSize:"11px" }}>{v}</span>;
}

function Dim({ children }) {
  return (
    <span style={{ color:"#4d5566", fontSize:"12px" }}>{children}</span>
  );
}