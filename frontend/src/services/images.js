const buildQuery = (params = {}) => {
  const esc = encodeURIComponent;
  return Object.keys(params)
    .filter(k => params[k] !== undefined && params[k] !== null && params[k] !== '')
    .map(k => `${esc(k)}=${esc(params[k])}`)
    .join('&');
}

const API_BASE = (process.env.REACT_APP_API_BASE || 'http://localhost:8000').replace(/\/$/, '');

// Normalize root so we don't accidentally create URLs like /api/api/...
const apiRoot = API_BASE.endsWith('/api') ? API_BASE : `${API_BASE}/api`;

export async function listImages(params = {}) {
  const q = buildQuery(params);
  const url = `${apiRoot}/generated-images/${q ? `?${q}` : ''}`;
  const resp = await fetch(url, { credentials: 'include' });
  // If backend returned HTML (e.g., CRA dev server or an error page), surface a clearer error
  const ct = resp.headers.get('content-type') || '';
  if (!resp.ok) {
    let body = '';
    try { body = await resp.text(); } catch (e) {}
    throw new Error(`HTTP ${resp.status}: ${body.slice(0,200)}`);
  }
  if (!ct.includes('application/json')) {
    const text = await resp.text();
    throw new Error(`Expected JSON but got: ${text.slice(0,200)}`);
  }
  return resp.json();
}

export default { listImages };
