import React, { useEffect, useState } from 'react';
import { listImages } from '../services/images';

export default function Gallery() {
  const [images, setImages] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);

  const [filters, setFilters] = useState({ topic: '', session_id: '', kind: '', date_from: '', date_to: '' });

  useEffect(() => {
    fetchPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  async function fetchPage(p = page) {
    setLoading(true);
    try {
      const params = {
        page: p,
        page_size: pageSize,
        ...filters,
      };
      const data = await listImages(params);
      setImages(data.images || []);
      setCount(data.count || 0);
      setTotalPages(data.total_pages || 1);
      setPage(data.page || p);
    } catch (e) {
      console.error('Failed to load images', e);
      setImages([]);
      setCount(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  }

  function onFilterChange(e) {
    const { name, value } = e.target;
    setFilters((s) => ({ ...s, [name]: value }));
  }

  async function applyFilters(ev) {
    ev && ev.preventDefault();
    setPage(1);
    await fetchPage(1);
  }

  function clearFilters() {
    setFilters({ topic: '', session_id: '', kind: '', date_from: '', date_to: '' });
    setPage(1);
    fetchPage(1);
  }

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ marginBottom: 12 }}>Galería de Imágenes Generadas</h2>

      <form onSubmit={applyFilters} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}>Tema</label>
          <input name="topic" placeholder="Tema" value={filters.topic} onChange={onFilterChange} />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}>Session</label>
          <input name="session_id" placeholder="Session ID" value={filters.session_id} onChange={onFilterChange} />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}>Tipo</label>
          <select name="kind" value={filters.kind} onChange={onFilterChange}>
            <option value="">(todos)</option>
            <option value="cover">Portada</option>
            <option value="question">Pregunta</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}>Desde</label>
          <input name="date_from" type="date" value={filters.date_from} onChange={onFilterChange} />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}>Hasta</label>
          <input name="date_to" type="date" value={filters.date_to} onChange={onFilterChange} />
        </div>

        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
          <button type="submit" style={{ padding: '6px 12px' }}>Filtrar</button>
          <button type="button" onClick={clearFilters} style={{ padding: '6px 12px' }}>Limpiar</button>
        </div>
      </form>

      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <label style={{ fontSize: 13, marginRight: 8 }}>Mostrar por página:</label>
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[12,20,36,48].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div style={{ fontSize: 13, color: '#666' }}>Mostrando {images.length} de {count} — Página {page} / {totalPages}</div>
      </div>

      {loading ? <div>Cargando...</div> : (
        <>
          {images.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#666' }}>No se encontraron imágenes con esos filtros.</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 16 }}>
              {images.map(img => (
                <figure key={img.id} style={{ margin: 0, background: '#ffffff', padding: 8, borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', overflow: 'hidden' }}>
                  <div style={{ position: 'relative', height: 160, background: '#f4f4f4' }}>
                    <a href={img.image_url} target="_blank" rel="noreferrer">
                      <img src={img.image_url} alt={`img-${img.id}`} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                    </a>
                    <div style={{ position: 'absolute', left: 8, top: 8, background: 'rgba(0,0,0,0.6)', color: '#fff', padding: '4px 8px', borderRadius: 12, fontSize: 12 }}>
                      {img.kind === 'cover' ? 'Portada' : 'Pregunta'}
                    </div>
                  </div>
                  <figcaption style={{ fontSize: 13, marginTop: 8, color: '#333' }}>
                    <div style={{ fontWeight: 600 }}>{img.session ? img.session.topic : ''}</div>
                    <div style={{ fontSize: 12, color: '#666' }}>{new Date(img.created).toLocaleString()}</div>
                  </figcaption>
                </figure>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16, alignItems: 'center' }}>
            <div style={{ color: '#666' }}>Mostrando {images.length} de {count}</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button disabled={page<=1} onClick={() => { const np = Math.max(1, page-1); setPage(np); fetchPage(np); }}>Anterior</button>
              <div style={{ minWidth: 120, textAlign: 'center' }}>Página {page} / {totalPages}</div>
              <button disabled={page >= totalPages} onClick={() => { const np = Math.min(totalPages, page+1); setPage(np); fetchPage(np); }}>Siguiente</button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
