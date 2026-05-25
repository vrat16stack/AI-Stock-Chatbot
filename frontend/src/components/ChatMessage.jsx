// ChatMessage.jsx
// Renders a single chat bubble.
// Parses **bold**, _italic_, `code`, bullet points from message text.
// Shows "View Full Analysis" button for analysis-type messages.

export default function ChatMessage({ message, persona, accentColor, onViewAnalysis }) {
  const isUser     = message.role === "user";
  const isAnalysis = message.type === "analysis";
  const isError    = message.type === "error";

  return (
    <div style={{
      display:        "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom:   "14px",
      gap:            "8px",
      alignItems:     "flex-start",
    }}>
      {/* Bot avatar */}
      {!isUser && (
        <div style={{
          width:36, height:36, borderRadius:"9px",
          background: "linear-gradient(135deg,#1e293b,#334155)",
          border:     "1px solid #30363d",
          display:    "flex", alignItems:"center",
          justifyContent:"center", fontSize:"15px",
          flexShrink:0, marginTop:"2px",
        }}>📈</div>
      )}

      <div style={{ maxWidth:"82%", minWidth:"60px" }}>
        {/* Bubble */}
        <div style={{
          background:   isUser ? "#1f2937"
                      : isError ? "#1a0e0e"
                      : "#161b22",
          border: `1px solid ${
            isUser     ? "#374151"
            : isError  ? "#7f1d1d"
            : isAnalysis ? accentColor + "44"
            : "#21262d"
          }`,
          borderRadius: isUser
            ? "16px 16px 4px 16px"
            : "4px 16px 16px 16px",
          padding:     "12px 16px",
          color:       "#e6edf3",
          fontSize:    "14px",
          lineHeight:  "1.75",
        }}>
          <FormattedText text={message.content} accent={accentColor} />
        </div>

        {/* View Full Analysis button */}
        {isAnalysis && message.analysis && (
          <button
            onClick={() => onViewAnalysis(message.analysis)}
            style={{
              marginTop:    "6px",
              background:   "transparent",
              border:       `1px solid ${accentColor}55`,
              borderRadius: "8px",
              color:        accentColor,
              fontSize:     "12px",
              fontWeight:   500,
              padding:      "5px 14px",
              cursor:       "pointer",
              display:      "flex",
              alignItems:   "center",
              gap:          "5px",
              transition:   "all 0.15s",
              fontFamily:   "inherit",
            }}
            onMouseEnter={e =>
              e.currentTarget.style.background = accentColor + "18"}
            onMouseLeave={e =>
              e.currentTarget.style.background = "transparent"}
          >
            📊 View Full Analysis
          </button>
        )}
      </div>
    </div>
  );
}


// ── Markdown-lite renderer ────────────────────────────────────────────────────

function FormattedText({ text, accent }) {
  const lines = (text || "").split("\n");
  return (
    <div>
      {lines.map((line, i) => {
        if (!line.trim()) {
          return <div key={i} style={{ height:"6px" }} />;
        }
        // Bullet points
        const isBullet = line.trimStart().startsWith("• ") ||
                         line.trimStart().startsWith("- ");
        if (isBullet) {
          const content = line.trimStart().slice(2);
          return (
            <div key={i} style={{
              display:"flex", gap:"8px", marginBottom:"3px",
            }}>
              <span style={{ color:accent, flexShrink:0, marginTop:"2px" }}>•</span>
              <span><Inline text={content} accent={accent} /></span>
            </div>
          );
        }
        return (
          <div key={i} style={{ marginBottom:"1px" }}>
            <Inline text={line} accent={accent} />
          </div>
        );
      })}
    </div>
  );
}

function Inline({ text, accent }) {
  // Parse **bold**, _italic_, `code`
  const parts = [];
  const regex = /(\*\*(.+?)\*\*|_(.+?)_|`(.+?)`)/g;
  let last = 0, m;

  while ((m = regex.exec(text)) !== null) {
    if (m.index > last)
      parts.push({ t: "text", v: text.slice(last, m.index) });

    if (m[0].startsWith("**"))
      parts.push({ t: "bold",   v: m[2] });
    else if (m[0].startsWith("_"))
      parts.push({ t: "italic", v: m[3] });
    else if (m[0].startsWith("`"))
      parts.push({ t: "code",   v: m[4] });

    last = m.index + m[0].length;
  }
  if (last < text.length)
    parts.push({ t: "text", v: text.slice(last) });

  return (
    <>
      {parts.map((p, i) => {
        if (p.t === "bold")
          return (
            <strong key={i} style={{ color:"#f0f6fc", fontWeight:600 }}>
              {p.v}
            </strong>
          );
        if (p.t === "italic")
          return (
            <em key={i} style={{ color:"#8b949e", fontStyle:"italic" }}>
              {p.v}
            </em>
          );
        if (p.t === "code")
          return (
            <code key={i} style={{
              background:   "#21262d",
              color:        accent,
              padding:      "1px 6px",
              borderRadius: "4px",
              fontSize:     "13px",
              fontFamily:   "monospace",
            }}>
              {p.v}
            </code>
          );
        return <span key={i}>{p.v}</span>;
      })}
    </>
  );
}