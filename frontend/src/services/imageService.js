const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

export async function fetchImageAssets({ sessionId, imageType, from, to, limit = 50, offset = 0 } = {}){
  const params = new URLSearchParams();
  if(sessionId) params.append('session_id', sessionId);
  if(imageType) params.append('image_type', imageType);
  if(from) params.append('from', from);
  if(to) params.append('to', to);
  params.append('limit', String(limit));
  params.append('offset', String(offset));

  const url = `${API_BASE}/image-assets/?${params.toString()}`;
  const resp = await fetch(url, { credentials: 'include' });
  if(!resp.ok) {
    const text = await resp.text();
    throw new Error(`fetch failed: ${resp.status} ${text.slice(0,200)}`);
  }
  return resp.json();
}
