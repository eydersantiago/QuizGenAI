import React, { useEffect, useState } from 'react';
import { fetchImageAssets } from '../services/imageService';
import '../estilos/ImageGallery.css';

export default function ImageGallery() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [sessionId, setSessionId] = useState('');
  const [imageType, setImageType] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const fetchList = async () => {
    setLoading(true);
    setError(null);
    try {
      // backend expects ISO datetimes for parse_datetime; convert date inputs to full ISO range
      const params = {};
      if (sessionId) params.sessionId = sessionId;
      if (imageType) params.imageType = imageType; // already mapped by select
      if (from) params.from = `${from}T00:00:00`;
      if (to) params.to = `${to}T23:59:59`;
      params.limit = 100;

      const resp = await fetchImageAssets({ sessionId: params.sessionId, imageType: params.imageType, from: params.from, to: params.to, limit: params.limit });
      // backend returns { total, count, items }
      const list = resp.items || resp.results || resp;
      setImages(Array.isArray(list) ? list : []);
    } catch (e) {
      console.error('Error fetching images', e);
      setError(e.message || String(e));
      setImages([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // load initial small list
    fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSearch = (e) => {
    e && e.preventDefault();
    fetchList();
  };

  const onClear = () => {
    setSessionId('');
    setImageType('');
    setFrom('');
    setTo('');
    setImages([]);
  };

  const fmt = (s) => {
    if (!s) return '';
    try {
      const d = new Date(s);
      return d.toLocaleString();
    } catch { return s; }
  };

  return (
    <div className="image-gallery-page">
      <h2>Galería de imágenes</h2>

      <form className="filters" onSubmit={onSearch}>
        <label>
          Quiz / Session ID:
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} placeholder="ID de sesión o quiz" />
        </label>

        <label>
          Tipo:
          <select value={imageType} onChange={(e) => setImageType(e.target.value)}>
            <option value="">Cualquiera</option>
            <option value="quiz">Pregunta</option>
            <option value="portada">Portada</option>
          </select>
        </label>

        <label>
          Desde:
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>

        <label>
          Hasta:
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>

        <div className="filter-actions">
          <button type="submit" className="primary">Buscar</button>
          <button type="button" onClick={onClear}>Limpiar</button>
        </div>
      </form>

      <div className="status-bar">
        {loading && <span>Cargando imágenes…</span>}
        {error && <span className="error">Error: {error}</span>}
        {!loading && !error && images.length === 0 && <span>No hay imágenes para mostrar.</span>}
      </div>

      <div className="image-grid">
        {images.map((img, idx) => (
          <div key={img.id || idx} className="image-card">
            <a href={img.image_url || img.image_path} target="_blank" rel="noreferrer">
              <img src={img.image_url || img.image_path} alt={img.name || ''} />
            </a>
            <div className="meta">
              <div className="meta-row"><strong>Tipo:</strong> {img.image_type || '-'} </div>
              <div className="meta-row"><strong>Quiz/Session:</strong> {img.session_id || '-'} </div>
              <div className="meta-row"><strong>Nombre:</strong> {img.name || img.image_path || '-'} </div>
              <div className="meta-row"><strong>Creado:</strong> {fmt(img.created_at)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
