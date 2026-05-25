// PersonaModal.jsx
// ─────────────────────────────────────────────────────────────
// Shows EVERY time the chatbot page is opened — no localStorage memory.
// User picks Investor or Trader → this drives all AI output formatting.
// ─────────────────────────────────────────────────────────────

import { useState } from "react";

export default function PersonaModal({ onSelect }) {
  const [selected,   setSelected]   = useState(null);
  const [animateOut, setAnimateOut] = useState(false);

  const confirm = () => {
    if (!selected) return;
    setAnimateOut(true);
    setTimeout(() => onSelect(selected), 360);
  };

  const accent = selected === "investor" ? "#16a34a"
               : selected === "trader"   ? "#0ea5e9"
               : "#374151";

  return (
    <div style={{
      position:       "fixed",
      inset:          0,
      background:     "rgba(0,0,0,0.72)",
      display:        "flex",
      alignItems:     "center",
      justifyContent: "center",
      padding:        "20px",
      fontFamily:     "'DM Sans','Segoe UI',sans-serif",
      zIndex:         999,
      opacity:        animateOut ? 0 : 1,
      transition:     "opacity 0.36s ease",
    }}>
      <div style={{
        background:  "#0d1117",
        border:      "1px solid #30363d",
        borderRadius:"18px",
        padding:     "36px 32px 32px",
        width:       "100%",
        maxWidth:    "500px",
        transform:   animateOut ? "scale(0.95)" : "scale(1)",
        transition:  "transform 0.36s ease",
      }}>

        {/* Icon + question */}
        <div style={{ textAlign: "center", marginBottom: "26px" }}>
          <div style={{
            width:         "48px",
            height:        "48px",
            borderRadius:  "12px",
            background:    "linear-gradient(135deg, #1a6b3a, #0ea5e9)",
            margin:        "0 auto 16px",
            display:       "flex",
            alignItems:    "center",
            justifyContent:"center",
            fontSize:      "22px",
          }}>📈</div>

          <h2 style={{
            color:       "#f0f6fc",
            fontSize:    "19px",
            fontWeight:  "600",
            margin:      "0 0 6px",
            letterSpacing:"-0.01em",
          }}>
            How do you define yourself?
          </h2>
          <p style={{
            color:      "#7d8590",
            fontSize:   "13px",
            margin:     0,
            lineHeight: "1.5",
          }}>
            Your choice shapes how the AI explains its analysis.
          </p>
        </div>

        {/* Cards */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "24px" }}>
          <PersonaCard
            id          = "investor"
            selected    = {selected === "investor"}
            onSelect    = {() => setSelected("investor")}
            label       = "Investor"
            tagline     = "Long-term · wealth creation"
            description = {
              "An investor in the stock market is a person that puts their money into shares " +
              "of a company. The main goal is to hold these shares for a long time, hoping the " +
              "company grows and the value of their investment increases, allowing them to make " +
              "a profit later."
            }
            pills       = {["Simple language", "Key highlights", "Easy entry levels"]}
            accent      = "#16a34a"
          />

          <PersonaCard
            id          = "trader"
            selected    = {selected === "trader"}
            onSelect    = {() => setSelected("trader")}
            label       = "Trader"
            tagline     = "Short-term · price action"
            description = {
              "A stock market trader is an individual that buys and sells stocks and other " +
              "financial assets frequently, sometimes within minutes or days to make a quick " +
              "profit from price movements."
            }
            pills       = {["Full technical detail", "All indicators", "Entry + SL + Target"]}
            accent      = "#0ea5e9"
          />
        </div>

        {/* Confirm button */}
        <button
          onClick  = {confirm}
          disabled = {!selected}
          style={{
            width:        "100%",
            padding:      "13px",
            borderRadius: "10px",
            border:       "none",
            background:   selected
              ? `linear-gradient(135deg, ${accent}, ${accent}cc)`
              : "#21262d",
            color:        selected ? "#fff" : "#4d5566",
            fontSize:     "14px",
            fontWeight:   "600",
            cursor:       selected ? "pointer" : "not-allowed",
            transition:   "all 0.2s ease",
            letterSpacing:"0.01em",
          }}
        >
          {selected
            ? `Continue as ${selected === "investor" ? "Investor" : "Trader"}  →`
            : "Select one to continue"}
        </button>

        <p style={{
          color:     "#4d5566",
          fontSize:  "11px",
          textAlign: "center",
          margin:    "12px 0 0",
        }}>
          You can switch mode anytime from the chat header.
        </p>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Sub-component: PersonaCard
// ─────────────────────────────────────────────────────────────
function PersonaCard({ id, selected, onSelect, label, tagline, description, pills, accent }) {
  return (
    <label
      htmlFor = {id}
      style   = {{
        display:    "block",
        background: selected ? `${accent}18` : "#161b22",
        border:     `1.5px solid ${selected ? accent : "#30363d"}`,
        borderRadius:"12px",
        padding:    "16px 18px",
        cursor:     "pointer",
        transition: "all 0.18s ease",
      }}
    >
      {/* Hidden radio */}
      <input
        type     = "radio"
        id       = {id}
        name     = "persona"
        value    = {id}
        checked  = {selected}
        onChange = {onSelect}
        style    = {{ position:"absolute", opacity:0, width:0, height:0 }}
      />

      {/* Row 1: radio dot + label */}
      <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"10px" }}>
        {/* Custom radio */}
        <div style={{
          width:       "18px",
          height:      "18px",
          borderRadius:"50%",
          border:      `2px solid ${selected ? accent : "#4d5566"}`,
          background:  selected ? accent : "transparent",
          flexShrink:  0,
          display:     "flex",
          alignItems:  "center",
          justifyContent:"center",
          transition:  "all 0.15s ease",
        }}>
          {selected && (
            <div style={{ width:"6px", height:"6px", borderRadius:"50%", background:"#fff" }} />
          )}
        </div>

        <div>
          <div style={{
            color:      selected ? "#f0f6fc" : "#c9d1d9",
            fontSize:   "15px",
            fontWeight: "600",
          }}>{label}</div>
          <div style={{
            color:    selected ? accent : "#7d8590",
            fontSize: "12px",
          }}>{tagline}</div>
        </div>
      </div>

      {/* Description */}
      <p style={{
        color:       "#7d8590",
        fontSize:    "12px",
        lineHeight:  "1.6",
        margin:      "0 0 12px",
        paddingLeft: "28px",
      }}>
        {description}
      </p>

      {/* Pills */}
      <div style={{ paddingLeft:"28px", display:"flex", flexWrap:"wrap", gap:"6px" }}>
        {pills.map(p => (
          <span key={p} style={{
            background:   selected ? `${accent}28` : "#21262d",
            color:        selected ? accent : "#4d5566",
            fontSize:     "11px",
            fontWeight:   "500",
            padding:      "3px 9px",
            borderRadius: "20px",
            border:       `0.5px solid ${selected ? accent + "55" : "#30363d"}`,
            transition:   "all 0.15s ease",
          }}>
            {p}
          </span>
        ))}
      </div>
    </label>
  );
}
