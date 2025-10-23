export function parseAnswerCommand(text) {
  if (!text) return null;
  const t = text.trim().toLowerCase();

  // Verdadero/Falso
  if (/\b(verdadero|cierto|verdad|true)\b/.test(t)) return { type: "vf", value: true };
  if (/\b(falso|mentira|false)\b/.test(t)) return { type: "vf", value: false };

  // Opción A/B/C/D (y "1".."4")
  const map = { a:0,b:1,c:2,d:3 };
  const m1 = t.match(/respuesta\s+([abcd])/i) || t.match(/opci[oó]n\s+([abcd])/i) || t.match(/\b([abcd])\b/);
  if (m1) return { type: "mcq", index: map[m1[1].toLowerCase()] };

  const m2 = t.match(/\b(opci[oó]n|respuesta)\s+(\d+)\b/) || t.match(/\b(\d+)\b/);
  if (m2) {
    const n = parseInt(m2[2] || m2[1], 10);
    if (!Number.isNaN(n) && n>=1 && n<=4) return { type:"mcq", index:n-1 };
  }

  // Respuesta corta (dictado libre)
  return { type: "short", text: t };
}
