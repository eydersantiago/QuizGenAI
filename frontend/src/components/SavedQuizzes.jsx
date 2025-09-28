import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  BookOpen, 
  Play, 
  Trash2, 
  Calendar, 
  Clock, 
  CheckCircle, 
  ArrowLeft,
  Search,
  Filter,
  BarChart3,
  BookmarkPlus
} from "lucide-react";
import Swal from "sweetalert2";
import "../estilos/SavedQuizzes.css";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

export default function SavedQuizzes() {
  const navigate = useNavigate();
  const [savedQuizzes, setSavedQuizzes] = useState([]);
  const [filteredQuizzes, setFilteredQuizzes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [statistics, setStatistics] = useState(null);
  const [showStats, setShowStats] = useState(false);

  useEffect(() => {
    loadSavedQuizzes();
    loadStatistics();
  }, []);

  useEffect(() => {
    filterQuizzes();
  }, [savedQuizzes, searchTerm, difficultyFilter, statusFilter]);

  const loadSavedQuizzes = async () => {
    try {
      const response = await fetch(`${API_BASE}/saved-quizzes/`);
      if (response.ok) {
        const data = await response.json();
        setSavedQuizzes(data.saved_quizzes || []);
      } else {
        throw new Error('Error al cargar cuestionarios');
      }
    } catch (error) {
      console.error('Error:', error);
      Swal.fire("Error", "No se pudieron cargar los cuestionarios guardados", "error");
    } finally {
      setLoading(false);
    }
  };

  const loadStatistics = async () => {
    try {
      const response = await fetch(`${API_BASE}/saved-quizzes/statistics/`);
      if (response.ok) {
        const data = await response.json();
        setStatistics(data);
      }
    } catch (error) {
      console.error('Error loading statistics:', error);
    }
  };

  const filterQuizzes = () => {
    let filtered = [...savedQuizzes];

    // Filtro por término de búsqueda
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(quiz => 
        quiz.title.toLowerCase().includes(term) ||
        quiz.topic.toLowerCase().includes(term)
      );
    }

    // Filtro por dificultad
    if (difficultyFilter) {
      filtered = filtered.filter(quiz => quiz.difficulty === difficultyFilter);
    }

    // Filtro por estado
    if (statusFilter) {
      if (statusFilter === "completed") {
        filtered = filtered.filter(quiz => quiz.is_completed);
      } else if (statusFilter === "in-progress") {
        filtered = filtered.filter(quiz => !quiz.is_completed);
      }
    }

    setFilteredQuizzes(filtered);
  };

  const handleLoadQuiz = async (quizId) => {
    try {
      // Primero obtener los datos del quiz guardado
      const response = await fetch(`${API_BASE}/saved-quizzes/${quizId}/`);
      
      if (response.ok) {
        const data = await response.json();
        const savedQuiz = data.saved_quiz;
        
        Swal.fire({
          title: "Quiz Cargado",
          text: "Continuando desde donde lo dejaste",
          icon: "success",
          timer: 1500
        });

        // Navegar pasando los datos del quiz guardado directamente
        navigate(`/quiz/saved-${quizId}`, {
          state: {
            savedQuizData: {
              quiz_id: savedQuiz.id,
              title: savedQuiz.title,
              questions: savedQuiz.questions,
              user_answers: savedQuiz.user_answers,
              current_question: savedQuiz.current_question,
              is_completed: savedQuiz.is_completed,
              topic: savedQuiz.topic,
              difficulty: savedQuiz.difficulty
            }
          }
        });
      } else {
        throw new Error('Error al cargar el quiz');
      }
    } catch (error) {
      console.error('Error:', error);
      Swal.fire("Error", "No se pudo cargar el cuestionario", "error");
    }
  };

  const handleDeleteQuiz = async (quizId, title) => {
    const result = await Swal.fire({
      title: "¿Estás seguro?",
      text: `¿Quieres eliminar "${title}"? Esta acción no se puede deshacer.`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sí, eliminar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#dc2626"
    });

    if (result.isConfirmed) {
      try {
        const response = await fetch(`${API_BASE}/saved-quizzes/${quizId}/`, {
          method: 'DELETE'
        });

        if (response.ok) {
          setSavedQuizzes(prev => prev.filter(quiz => quiz.id !== quizId));
          Swal.fire("Eliminado", "El cuestionario ha sido eliminado", "success");
        } else {
          throw new Error('Error al eliminar');
        }
      } catch (error) {
        console.error('Error:', error);
        Swal.fire("Error", "No se pudo eliminar el cuestionario", "error");
      }
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getProgressColor = (percentage) => {
    if (percentage === 100) return "#16a34a"; // green-600
    if (percentage >= 50) return "#f59e0b"; // amber-500
    return "#ef4444"; // red-500
  };

  const getDifficultyColor = (difficulty) => {
    switch (difficulty) {
      case "Fácil": return "#10b981"; // emerald-500
      case "Media": return "#f59e0b"; // amber-500
      case "Difícil": return "#ef4444"; // red-500
      default: return "#6b7280"; // gray-500
    }
  };

  if (loading) {
    return (
      <div className="saved-quizzes-container">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Cargando cuestionarios guardados...</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div 
      className="saved-quizzes-container"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Header */}
      <div className="header-section">
        <div className="header-content">
          <button
            onClick={() => navigate('/')}
            className="back-button"
          >
            <ArrowLeft size={20} />
            Volver al Inicio
          </button>
          
          <div className="header-title">
            <h1>
              <BookOpen size={32} />
              Mis Cuestionarios Guardados
            </h1>
            <p>Gestiona y continúa tus cuestionarios</p>
          </div>

          <div className="header-actions">
            <button
              onClick={() => setShowStats(!showStats)}
              className="stats-button"
            >
              <BarChart3 size={20} />
              {showStats ? "Ocultar" : "Ver"} Estadísticas
            </button>
          </div>
        </div>

        {/* Estadísticas */}
        <AnimatePresence>
          {showStats && statistics && (
            <motion.div 
              className="statistics-panel"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{statistics.statistics.total_quizzes}</div>
                  <div className="stat-label">Total Cuestionarios</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{statistics.statistics.completed_quizzes}</div>
                  <div className="stat-label">Completados</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{statistics.statistics.in_progress_quizzes}</div>
                  <div className="stat-label">En Progreso</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{statistics.statistics.completion_rate}%</div>
                  <div className="stat-label">Tasa de Completitud</div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Filtros y búsqueda */}
      <div className="filters-section">
        <div className="search-box">
          <Search size={20} />
          <input
            type="text"
            placeholder="Buscar por título o tema..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="filters">
          <select
            value={difficultyFilter}
            onChange={(e) => setDifficultyFilter(e.target.value)}
          >
            <option value="">Todas las dificultades</option>
            <option value="Fácil">Fácil</option>
            <option value="Media">Media</option>
            <option value="Difícil">Difícil</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">Todos los estados</option>
            <option value="completed">Completados</option>
            <option value="in-progress">En Progreso</option>
          </select>
        </div>
      </div>

      {/* Lista de cuestionarios */}
      <div className="quizzes-grid">
        <AnimatePresence>
          {filteredQuizzes.length === 0 ? (
            <motion.div 
              className="empty-state"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <BookmarkPlus size={64} />
              <h3>No hay cuestionarios guardados</h3>
              <p>Los cuestionarios que guardes aparecerán aquí</p>
              <button
                onClick={() => navigate('/')}
                className="btn btn-primary"
              >
                Crear Nuevo Cuestionario
              </button>
            </motion.div>
          ) : (
            filteredQuizzes.map((quiz) => (
              <motion.div
                key={quiz.id}
                className="quiz-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                whileHover={{ scale: 1.02 }}
              >
                <div className="quiz-header">
                  <h3>{quiz.title}</h3>
                  <div className="quiz-actions">
                    <button
                      onClick={() => handleLoadQuiz(quiz.id)}
                      className="action-button load"
                      title="Cargar cuestionario"
                    >
                      <Play size={16} />
                    </button>
                    <button
                      onClick={() => handleDeleteQuiz(quiz.id, quiz.title)}
                      className="action-button delete"
                      title="Eliminar cuestionario"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>

                <div className="quiz-info">
                  <div className="info-row">
                    <span className="label">Tema:</span>
                    <span className="value">{quiz.topic}</span>
                  </div>
                  
                  <div className="info-row">
                    <span className="label">Dificultad:</span>
                    <span 
                      className="difficulty-badge"
                      style={{ backgroundColor: getDifficultyColor(quiz.difficulty) }}
                    >
                      {quiz.difficulty}
                    </span>
                  </div>

                  <div className="info-row">
                    <span className="label">Progreso:</span>
                    <div className="progress-info">
                      <div className="progress-bar">
                        <div 
                          className="progress-fill"
                          style={{ 
                            width: `${quiz.progress_percentage}%`,
                            backgroundColor: getProgressColor(quiz.progress_percentage)
                          }}
                        />
                      </div>
                      <span className="progress-text">
                        {quiz.answered_count}/{quiz.total_questions} ({quiz.progress_percentage}%)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="quiz-footer">
                  <div className="date-info">
                    <div className="date-item">
                      <Calendar size={14} />
                      <span>Creado: {formatDate(quiz.created_at)}</span>
                    </div>
                    <div className="date-item">
                      <Clock size={14} />
                      <span>Último acceso: {formatDate(quiz.last_accessed)}</span>
                    </div>
                  </div>
                  
                  {quiz.is_completed && (
                    <div className="completion-badge">
                      <CheckCircle size={16} />
                      Completado
                    </div>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}