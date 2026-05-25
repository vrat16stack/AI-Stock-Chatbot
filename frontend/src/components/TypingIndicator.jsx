// TypingIndicator.jsx
// Animated three-dot indicator shown while the API is processing.

export default function TypingIndicator({ accentColor }) {
  return (
    <div style={{
      display:     "flex",
      alignItems:  "flex-start",
      gap:         "8px",
      marginBottom:"14px",
    }}>
      {/* Bot avatar */}
      <div style={{
        width:36, height:36, borderRadius:"9px",
        background: "linear-gradient(135deg,#1e293b,#334155)",
        border:     "1px solid #30363d",
        display:    "flex", alignItems:"center",
        justifyContent:"center", fontSize:"15px",
        flexShrink: 0,
      }}>📈</div>

      {/* Bubble with dots */}
      <div style={{
        background:   "#161b22",
        border:       "1px solid #21262d",
        borderRadius: "4px 16px 16px 16px",
        padding:      "14px 18px",
        display:      "flex",
        alignItems:   "center",
        gap:          "5px",
      }}>
        {[0, 1, 2].map(i => (
          <div
            key={i}
            style={{
              width:           "7px",
              height:          "7px",
              borderRadius:    "50%",
              background:      accentColor || "#4d5566",
              opacity:         0.6,
              animation:       "typingBounce 1.2s ease-in-out infinite",
              animationDelay:  `${i * 0.2}s`,
            }}
          />
        ))}
        <style>{`
          @keyframes typingBounce {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
            40%            { transform: scale(1.1); opacity: 1;   }
          }
        `}</style>
      </div>
    </div>
  );
}
