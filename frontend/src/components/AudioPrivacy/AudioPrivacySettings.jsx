// frontend/src/components/AudioPrivacy/AudioPrivacySettings.jsx

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AudioPrivacySettings.css';

const AudioPrivacySettings = () => {
  const [preferences, setPreferences] = useState({
    save_audio: true,
    save_transcriptions: true
  });
  const [sessions, setSessions] = useState([]);
  const [deletionHistory, setDeletionHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState('preferences');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [prefRes, sessRes, histRes] = await Promise.all([
        axios.get('/api/audio-privacy/preferences/'),
        axios.get('/api/audio-privacy/sessions/'),
        axios.get('/api/audio-privacy/deletion_history/')
      ]);

      setPreferences(prefRes.data.preferences);
      setSessions(sessRes.data.sessions);
      setDeletionHistory(histRes.data.deletion_history);
    } catch (error) {
      showMessage('Error al cargar datos de privacidad', 'error');
    } finally {
      setLoading(false);
    }
  };

  const updatePreferences = async (updates) => {
    try {
      const response = await axios.patch('/api/audio-privacy/update_preferences/', updates);
      setPreferences(response.data.preferences);
      showMessage('Preferencias actualizadas', 'success');
    } catch (error) {
      showMessage('Error al actualizar preferencias', 'error');
    }
  };

  const deleteSession = async (sessionId) => {
    if (!window.confirm('¿Estás seguro de eliminar esta sesión y todos sus datos?')) {
      return;
    }

    try {
      await axios.post('/api/audio-privacy/delete_session/', { session_id: sessionId });
      showMessage('Sesión eliminada exitosamente', 'success');
      loadData();
    } catch (error) {
      showMessage('Error al eliminar sesión', 'error');
    }
  };

  const deleteAllSessions = async () => {
    if (!window.confirm('¿Estás seguro de eliminar TODAS tus sesiones de audio? Esta acción no se puede deshacer.')) {
      return;
    }

    try {
      const response = await axios.post('/api/audio-privacy/delete_all_sessions/');
      showMessage(response.data.message, 'success');
      loadData();
    } catch (error) {
      showMessage('Error al eliminar sesiones', 'error');
    }
  };

  const showMessage = (text, type) => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
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
              checked={preferences.save_audio}
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
              checked={preferences.save_transcriptions}
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
              {sessions.map(session => (
                <div key={session.session_id} className="session-card">
                  <div className="session-info">
                    <div className="session-id">
                      <strong>Sesión:</strong> {session.session_id.substring(0, 8)}...
                    </div>
                    <div className="session-meta">
                      <span>📅 {new Date(session.created_at).toLocaleString('es-CO')}</span>
                      <span>🎤 {session.audio_count} audios</span>
                      <span>📝 {session.transcription_count} transcripciones</span>
                    </div>
                    <div className="session-expires">
                      Expira: {new Date(session.expires_at).toLocaleString('es-CO')}
                    </div>
                  </div>
                  <button
                    className="btn btn-danger-sm"
                    onClick={() => deleteSession(session.session_id)}
                    aria-label={`Eliminar sesión ${session.session_id}`}
                  >
                    🗑️ Eliminar
                  </button>
                </div>
              ))}
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
                  {deletionHistory.map((audit, index) => (
                    <tr key={index}>
                      <td>{new Date(audit.deleted_at).toLocaleString('es-CO')}</td>
                      <td>{audit.session_id.substring(0, 8)}...</td>
                      <td>
                        <span className={`method-badge method-${audit.deletion_method}`}>
                          {audit.deletion_method === 'user_request' && '👤 Usuario'}
                          {audit.deletion_method === 'user_request_all' && '👤 Usuario (todas)'}
                          {audit.deletion_method === 'ttl_expired' && '⏰ TTL expirado'}
                          {audit.deletion_method === 'admin' && '🔧 Admin'}
                        </span>
                      </td>
                      <td>
                        {audit.items_deleted.audio} audios, {audit.items_deleted.transcriptions} transcripciones
                      </td>
                    </tr>
                  ))}
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