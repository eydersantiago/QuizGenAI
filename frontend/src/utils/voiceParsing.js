// frontend/src/utils/voiceParsing.js
// Utilidades para extraer 'slots' (count, topic, difficulty, index) de texto natural

const NUM_WORDS = {
  cero:0, uno:1, dos:2, tres:3, cuatro:4, cinco:5, seis:6, siete:7, ocho:8, nueve:9, diez:10,
  once:11, doce:12, trece:13, catorce:14, quince:15
};

const ORDINALS = {
  primera:1, primero:1, segunda:2, segundo:2, tercera:3, tercero:3, cuarta:4, cuarto:4,
  quinta:5, quinto:5, sexta:6, sexto:6
};

function wordToNumber(w) {
  if (!w) return null;
  const n = Number(w);
  if (!Number.isNaN(n)) return n;
  const lw = w.toLowerCase();
  if (NUM_WORDS[lw] !== undefined) return NUM_WORDS[lw];
  if (ORDINALS[lw] !== undefined) return ORDINALS[lw];
  return null;
}

export function extractSlotsFromText(text = '') {
  const t = (text || '').toString().toLowerCase();
  const slots = {};

  // count: look for digits or number words
  const mNum = t.match(/\b(\d{1,3})\b/);
  if (mNum) {
    slots.count = Number(mNum[1]);
  } else {
    // try words
    for (const w of Object.keys(NUM_WORDS)) if (new RegExp(`\\b${w}\\b`).test(t)) { slots.count = NUM_WORDS[w]; break; }
    if (slots.count === undefined) {
      for (const w of Object.keys(ORDINALS)) if (new RegExp(`\\b${w}\\b`).test(t)) { slots.count = ORDINALS[w]; break; }
    }
  }

  // index: look for 'pregunta 3' or ordinal words
  const mIdx = t.match(/pregunta[s]?\s*(?:numero|nro|n\.?|#)?\s*(\d{1,3})/);
  if (mIdx) slots.index = Number(mIdx[1]);
  else {
    for (const w of Object.keys(ORDINALS)) if (new RegExp(`\\b${w}\\b`).test(t)) { slots.index = ORDINALS[w]; break; }
  }

  // topic: phrase after 'sobre' or 'de' or 'acerca de'
  // topic: support several natural patterns: 'sobre X', 'de X', 'acerca de X', but also 'tema: X', 'tema, X', 'tema X', 'el tema es X'
  let mTopic = t.match(/(?:sobre|de|acerca de)\s+([a-záéíóúñ0-9\s]+)/);
  if (!mTopic) {
    mTopic = t.match(/(?:tema|temas)\s*(?:es|son|:|,)?\s*([a-záéíóúñ0-9\s]+)/);
  }
  if (!mTopic) {
    // catch patterns like 'el tema es algoritmos' or 'el tema: algoritmos'
    mTopic = t.match(/el\s+tema(?:\s+es)?\s*(?::|,)?\s*([a-záéíóúñ0-9\s]+)/);
  }
  if (mTopic) {
    // trim possible trailing words like 'dificultad' or 'dificil' etc and punctuation
    let topic = (mTopic[1] || '').trim().replace(/[.,;!?]$/,'');
    topic = topic.replace(/(dificultad|f[aá]cil|medio|intermedio|dif[ií]cil).*$/,'').trim();
    slots.topic = topic;
  }

  // difficulty
  // Accept common Spanish variants: 'fácil', 'facil', 'sencillo' -> Fácil
  if (/\b(f(a|á)cil|facil|sencillo)\b/.test(t)) slots.difficulty = 'Fácil';
  // Accept 'media' and 'medio' as well as 'intermedio/intermedia' -> Media
  else if (/\b(medi[oa]|intermedio|intermedia)\b/.test(t)) slots.difficulty = 'Media';
  // Difficult variants -> Difícil
  else if (/\b(dif(i|í)cil|dificil|complicad)\b/.test(t)) slots.difficulty = 'Difícil';

  return slots;
}

/**
 * Extrae múltiples pares tipo+cantidad desde texto natural.
 * Ejemplos: "3 opción múltiple y 2 VF", "opción múltiple 4, vf 2 y corta 1"
 * Retorna un objeto con keys 'mcq','vf','short' cuando se detectan.
 */
export function extractTypeCounts(text = '') {
  const t = (text || '').toString().toLowerCase();
  const out = {};

  // mapa de aliases de tipo -> canonical
  const typeMap = [
    // opción múltiple: varias formas incluidas 'selección múltiple', 'alternativa', 'multiple choice'
    { re: /opci[oó]n(?:es)?\s+m(?:u|ú)ltiple|m(?:u|ú)ltiple|opci[oó]n|mcq|selecci[oó]n\s+m(?:u|ú)ltiple|alternativa|alternativas|multiple\s*choice|multiplechoice|opciones\s+multiples/, canon: 'mcq' },
    // VF: detecta 'vf', 'v/f', 'v o f', 'verdadero/falso', 'verdadero' y variantes
    { re: /\b(vf|v\/f|v\s*o\s*f|v\s+f|verdader[oa]s?|verdadero|fals[oa]s?|falso|verdadero\s+falso)\b/, canon: 'vf' },
    // Respuesta corta / dictado libre
    { re: /corta|respuesta corta|short|texto|abierta|respuesta abierta|escribe|redacta/, canon: 'short' }
  ];

  // helper convierte palabra/num a número
  const parseNum = (s) => {
    if (!s) return null;
    const n = Number(s.replace(/[^0-9]/g, ''));
    if (!Number.isNaN(n) && n !== 0) return n;
    const wn = wordToNumber(s);
    return wn;
  };

  // patrón global para 'N tipo' o 'tipo N'
  const combinedPatterns = [
    // número antes del tipo: '3 opción múltiple'
    /\b(\d{1,2}|\b(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\b)\s*(?:pregunta[s]?\s*(?:de)?\s*)?(opci[oó]n(?:es)?\s+m(?:u|ú)ltiple|m(?:u|ú)ltiple|opci[oó]n|mcq|v\/f|vf|v\s+f|verdader[oa]s?|fals[oa]s?|falso|verdadero|corta|respuesta corta|short|texto)\b/gi,
    // tipo antes del número: 'opción múltiple 3'
    /\b(opci[oó]n(?:es)?\s+m(?:u|ú)ltiple|m(?:u|ú)ltiple|opci[oó]n|mcq|v\/f|vf|v\s+f|verdader[oa]s?|fals[oa]s?|falso|verdadero|corta|respuesta corta|short|texto)\s*(?:de\s*)?(\d{1,2}|\b(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\b)\b/gi
  ];

  for (const pat of combinedPatterns) {
    let m;
    while ((m = pat.exec(t)) !== null) {
      // m[1] may be number or type depending on pattern
      let numPart = m[1];
      let typePart = m[2];
      // if pattern reversed, swap
      if (!typePart) { numPart = m[1]; typePart = m[2]; }
      // ensure we have both
      if (!numPart || !typePart) continue;
      const n = parseNum(numPart);
      if (!n) continue;
      // normalize typePart to canonical
      let canon = null;
      for (const tm of typeMap) {
        if (tm.re.test(typePart)) { canon = tm.canon; break; }
      }
      if (!canon) continue;
      out[canon] = Math.max(0, Math.min(20, n));
    }
  }

  // También soportar casos simples cuando sólo hay un número y la mención contiene 'vf' o 'verdadero' etc
  if (Object.keys(out).length === 0) {
    // si existe un número y alguna mención de tipo en el texto en otra parte
    const anyNum = t.match(/\b(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b/);
    if (anyNum) {
      const maybe = parseNum(anyNum[1]);
      if (maybe) {
        for (const tm of typeMap) {
          if (tm.re.test(t)) { out[tm.canon] = Math.max(0, Math.min(20, maybe)); break; }
        }
      }
    }
  }

  return out;
}

/**
 * Obtener un slot dado un objeto result (posiblemente con slots) o texto
 * @param {Object|string} resultOrText - puede ser el objeto de intención o un texto
 * @param {string} name - nombre del slot: 'count'|'topic'|'difficulty'|'index'
 */
export function getSlot(resultOrText, name) {
  if (!resultOrText) return null;
  // si es objeto con slots
  if (typeof resultOrText === 'object' && resultOrText.slots) {
    if (resultOrText.slots[name] !== undefined) return resultOrText.slots[name];
  }
  const text = (typeof resultOrText === 'string') ? resultOrText : (resultOrText.text || resultOrText.transcript || '');
  const slots = extractSlotsFromText(text);
  return slots[name] !== undefined ? slots[name] : null;
}

export default { extractSlotsFromText, getSlot };
export function parseAnswerCommand(text) {
  if (!text) return null;
  const t = text.trim().toLowerCase();

  // Verdadero/Falso
  if (/\b(verdadero|cierto|verdad|true|si|sí|afirmativo|correcto)\b/.test(t)) return { type: "vf", value: true };
  if (/\b(falso|mentira|false|no|negativo|incorrecto)\b/.test(t)) return { type: "vf", value: false };

  // Opción A/B/C/D (y "1".."4")
  const map = { a:0,b:1,c:2,d:3 };
  // capturar letras con variantes: 'c', 'c.', 'c)', 'la c', 'opcion c', 'respuesta c', 'c ' etc
  const m1 = t.match(/respuesta\s*[:\-]?\s*([abcd])\b/i) || t.match(/opci[oó]n\s*[:\-]?\s*([abcd])\b/i) || t.match(/\b([abcd])\b/i) || t.match(/\b([abcd])\s*[\.)]/i);
  if (m1) return { type: "mcq", index: map[(m1[1] || m1[0]).toLowerCase()] };

  // números como 'opcion 2', '2', 'segunda', 'la 2.'
  const m2 = t.match(/\b(?:opci[oó]n|respuesta|alternativa)?\s*[:\-]?\s*(\d{1,2}|uno|dos|tres|cuatro|primera|segunda|tercera|cuarta)\b/i);
  if (m2) {
    let num = m2[1];
    // normalizar palabras ordinales y numWords
    const nmap = { uno:1,dos:2,tres:3,cuatro:4,primera:1,primero:1,segunda:2,segundo:2,tercera:3,tercero:3,cuarta:4,cuarto:4 };
    if (nmap[num]) num = nmap[num];
    const n = parseInt(num, 10);
    if (!Number.isNaN(n) && n>=1 && n<=4) return { type:"mcq", index:n-1 };
  }

  // Respuesta corta (dictado libre)
  return { type: "short", text: t };
}
