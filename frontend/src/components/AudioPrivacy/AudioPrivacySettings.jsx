// frontend/src/components/AudioPrivacy/AudioPrivacySettings.jsx

import React, { useState, useEffect } from 'react';
import './AudioPrivacySettings.css';

const DEFAULT_PREFS = {
  save_audio: true,
  save_transcriptions: true,
};

const BASE = '/api/audio-privacy';

function coerceBool(v, fallback = false) {
  if (typeof v === 'boolean') return v;
  if (v === 'true') return true;
  if (v === 'false') return false;
  return fallback;
}

function parsePreferences(data) {
  const src = data?.preferences ?? data ?? {};
  return {
    save_audio: coerceBool(src.save_audio, DEFAULT_PREFS.save_audio),
    save_transcriptions: coerceBool(src.save_transcriptions, DEFAULT_PREFS.save_transcriptions),
  };
}

function parseSessions(data) {
  const raw = data?.sessions ?? data ?? [];
  return Array.isArray(raw) ? raw : [];
}

function parseDeletionHistory(data) {
  const raw = data?.deletion_history ?? data ?? [];
  return Array.isArray(raw) ? raw : [];
}

// Helper fetch con JSON y manejo de errores
async function apiFetch(path, { method = 'GET', data, headers } = {}) {
  const init = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(headers || {}),
    },
  };
  if (data !== undefined) init.body = JSON.stringify(data);

  const resp = await fetch(`${BASE}${path}`, init);
  let json = null;
  try { json = await resp.json(); } catch { /* puede no devolver json */ }
  if (!resp.ok) {
    const msg = (json && (json.detail || json.error || json.message)) || `HTTP ${resp.status}`;
    const err = new Error(msg);
    err.status = resp.status;
    err.payload = json;
    throw err;
  }
  return json ?? {};
}

const AudioPrivacySettings = () => {
  const [preferences, setPreferences] = useState(DEFAULT_PREFS);
  const [sessions, setSessions] = useState([]);
  const [deletionHistory, setDeletionHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState('preferences');

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showMessage = (text, type) => {
    setMessage({ text, type });
    window.clearTimeout(showMessage._t);
    showMessage._t = window.setTimeout(() => setMessage(null), 5000);
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [prefRes, sessRes, histRes] = await Promise.all([
        apiFetch('/preferences/'),
        apiFetch('/sessions/'),
        apiFetch('/deletion_history/')
      ]);

      setPreferences(parsePreferences(prefRes));
      setSessions(parseSessions(sessRes));
      setDeletionHistory(parseDeletionHistory(histRes));
    } catch (error) {
      console.error('Audio privacy load error:', error);
      showMessage('Error al cargar datos de privacidad', 'error');
      // Fallbacks seguros
      setPreferences((p) => p ?? DEFAULT_PREFS);
      setSessions((s) => Array.isArray(s) ? s : []);
      setDeletionHistory((h) => Array.isArray(h) ? h : []);
    } finally {
      setLoading(false);
    }
  };

  const updatePreferences = async (updates) => {
    try {
      // Acepta PATCH plano {save_audio:bool} / {save_transcriptions:bool}
      const response = await apiFetch('/update_preferences/', { method: 'PATCH', data: updates });
      setPreferences(parsePreferences(response));
      showMessage('Preferencias actualizadas', 'success');
    } catch (error) {
      console.error('Update preferences error:', error);
      showMessage('Error al actualizar preferencias', 'error');
    }
  };

  const deleteSession = async (sessionId) => {
    if (!window.confirm('¿Estás seguro de eliminar esta sesión y todos sus datos?')) {
      return;
    }
    try {
      await apiFetch('/delete_session/', { method: 'POST', data: { session_id: sessionId } });
      showMessage('Sesión eliminada exitosamente', 'success');
      await loadData();
    } catch (error) {
      console.error('Delete session error:', error);
      showMessage('Error al eliminar sesión', 'error');
    }
  };

  const deleteAllSessions = async () => {
    if (!window.confirm('¿Estás seguro de eliminar TODAS tus sesiones de audio? Esta acción no se puede deshacer.')) {
      return;
    }
    try {
      const response = await apiFetch('/delete_all_sessions/', { method: 'POST' });
      const msg = response?.message || 'Sesiones eliminadas';
      showMessage(msg, 'success');
      await loadData();
    } catch (error) {
      console.error('Delete all sessions error:', error);
      showMessage('Error al eliminar sesiones', 'error');
    }
  };

  if (loading) {
    return <div className="loading">Cargando configuración de privacidad...</div>;
  }

  return (
    <div className="audio-privacy-settings">
      <h1>Privacidad de Audio</h1>

      {message && (
        <div className={`message message-${message.type}`} role="alert">
          {message.text}
        </div>
      )}

      <div className="tabs">
        <button
          className={activeTab === 'preferences' ? 'active' : ''}
          onClick={() => setActiveTab('preferences')}
        >
          Preferencias
        </button>
        <button
          className={activeTab === 'sessions' ? 'active' : ''}
          onClick={() => setActiveTab('sessions')}
        >
          Sesiones ({sessions.length})
        </button>
        <button
          className={activeTab === 'history' ? 'active' : ''}
          onClick={() => setActiveTab('history')}
        >
          Historial
        </button>
      </div>

      {activeTab === 'preferences' && (
        <div className="tab-content">
          <h2>Preferencias de recolección</h2>

          <label className="toggle-setting">
            <input
              type="checkbox"
              checked={!!preferences.save_audio}
              onChange={(e) => updatePreferences({ save_audio: e.target.checked })}
            />
            <span>
              <strong>Guardar grabaciones de audio</strong>
              <span className="setting-desc">
                Si está desactivado, no se almacenarán las grabaciones de audio (solo se procesarán en tiempo real)
              </span>
            </span>
          </label>

          <label className="toggle-setting">
            <input
              type="checkbox"
              checked={!!preferences.save_transcriptions}
              onChange={(e) => updatePreferences({ save_transcriptions: e.target.checked })}
            />
            <span>
              <strong>Guardar transcripciones</strong>
              <span className="setting-desc">
                Si está desactivado, no se almacenarán las transcripciones de texto
              </span>
            </span>
          </label>

          <div className="info-box">
            <h3>🔒 Seguridad</h3>
            <ul>
              <li>Todos los datos se almacenan cifrados</li>
              <li>Se eliminan automáticamente después de 24 horas</li>
              <li>Información personal redactada automáticamente</li>
            </ul>
          </div>
        </div>
      )}

      {activeTab === 'sessions' && (
        <div className="tab-content">
          <div className="section-header">
            <h2>Sesiones de audio activas</h2>
            {sessions.length > 0 && (
              <button
                className="btn btn-danger-outline"
                onClick={deleteAllSessions}
              >
                Eliminar todas
              </button>
            )}
          </div>

          {sessions.length === 0 ? (
            <p className="empty-state">No tienes sesiones de audio activas</p>
          ) : (
            <div className="sessions-list">
              {sessions.map((session) => {
                const sid = session?.session_id || '';
                const createdAt = session?.created_at ? new Date(session.created_at) : null;
                const expiresAt = session?.expires_at ? new Date(session.expires_at) : null;
                const audioCount = Number(session?.audio_count ?? 0);
                const transcriptionCount = Number(session?.transcription_count ?? 0);

                return (
                  <div key={sid || Math.random()} className="session-card">
                    <div className="session-info">
                      <div className="session-id">
                        <strong>Sesión:</strong> {sid ? `${sid.substring(0, 8)}...` : '(sin id)'}
                      </div>
                      <div className="session-meta">
                        <span>📅 {createdAt ? createdAt.toLocaleString('es-CO') : '—'}</span>
                        <span>🎤 {audioCount} audios</span>
                        <span>📝 {transcriptionCount} transcripciones</span>
                      </div>
                      <div className="session-expires">
                        Expira: {expiresAt ? expiresAt.toLocaleString('es-CO') : '—'}
                      </div>
                    </div>
                    <button
                      className="btn btn-danger-sm"
                      onClick={() => sid && deleteSession(sid)}
                      disabled={!sid}
                      aria-label={`Eliminar sesión ${sid || ''}`}
                    >
                      🗑️ Eliminar
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="tab-content">
          <h2>Historial de eliminaciones</h2>

          {deletionHistory.length === 0 ? (
            <p className="empty-state">No hay historial de eliminaciones</p>
          ) : (
            <div className="history-list">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Sesión</th>
                    <th>Método</th>
                    <th>Elementos eliminados</th>
                  </tr>
                </thead>
                <tbody>
                  {deletionHistory.map((audit, index) => {
                    const deletedAt = audit?.deleted_at ? new Date(audit.deleted_at) : null;
                    const sid = audit?.session_id || '';
                    const method = audit?.deletion_method || '';
                    const audio = Number(audit?.items_deleted?.audio ?? 0);
                    const trans = Number(audit?.items_deleted?.transcriptions ?? 0);

                    return (
                      <tr key={`${sid}-${index}`}>
                        <td>{deletedAt ? deletedAt.toLocaleString('es-CO') : '—'}</td>
                        <td>{sid ? `${sid.substring(0, 8)}...` : '—'}</td>
                        <td>
                          <span className={`method-badge method-${method}`}>
                            {method === 'user_request' && '👤 Usuario'}
                            {method === 'user_request_all' && '👤 Usuario (todas)'}
                            {method === 'ttl_expired' && '⏰ TTL expirado'}
                            {method === 'admin' && '🔧 Admin'}
                            {!['user_request','user_request_all','ttl_expired','admin'].includes(method) && '—'}
                          </span>
                        </td>
                        <td>{audio} audios, {trans} transcripciones</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AudioPrivacySettings;
