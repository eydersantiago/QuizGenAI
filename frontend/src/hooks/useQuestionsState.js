import { useReducer, useCallback } from 'react';
import { useImmerReducer } from 'use-immer';

/**
 * Reducer para manejar el estado de preguntas con Immer
 * Permite actualizaciones inmutables de forma más limpia
 */
function questionsReducer(draft, action) {
  switch (action.type) {
    case 'INIT_QUESTIONS':
      return action.questions.map((q, idx) => ({
        ...q,
        originalIndex: idx,
        isModified: false,
        isNew: false,
        id: q.id || `q-${idx}`,
      }));

    case 'EDIT_QUESTION':
      const question = draft.find(q => q.id === action.id);
      if (question) {
        question.question = action.text;
        question.isModified = true;
      }
      break;

    case 'EDIT_OPTION':
      const qWithOption = draft.find(q => q.id === action.questionId);
      if (qWithOption && qWithOption.options) {
        qWithOption.options[action.optionIndex] = action.text;
        qWithOption.isModified = true;
      }
      break;

    case 'DUPLICATE_QUESTION':
      const original = draft.find(q => q.id === action.id);
      if (original) {
        const newQuestion = {
          ...original,
          id: `q-${Date.now()}-${Math.random()}`,
          isNew: true,
          isModified: false,
          originalIndex: draft.length,
        };
        draft.push(newQuestion);
      }
      break;

    case 'DELETE_QUESTION':
      const indexToDelete = draft.findIndex(q => q.id === action.id);
      if (indexToDelete !== -1) {
        draft.splice(indexToDelete, 1);
      }
      break;

    case 'REPLACE_QUESTION':
      const indexToReplace = draft.findIndex(q => q.id === action.id);
      if (indexToReplace !== -1) {
        draft[indexToReplace] = {
          ...action.newQuestion,
          id: action.id,
          isModified: false,
          isNew: false,
        };
      }
      break;

    case 'SET_LOADING':
      const qToLoad = draft.find(q => q.id === action.id);
      if (qToLoad) {
        qToLoad.isLoading = action.isLoading;
      }
      break;

    case 'RESET_MODIFICATIONS':
      draft.forEach(q => {
        q.isModified = false;
        q.isNew = false;
      });
      break;

    default:
      break;
  }
}

/**
 * Hook personalizado para manejar el estado de preguntas con optimizaciones
 * Usa useImmerReducer para actualizaciones inmutables eficientes
 *
 * @param {Array} initialQuestions - Array inicial de preguntas
 * @returns {Object} - Estado y funciones para manipular preguntas
 */
export function useQuestionsState(initialQuestions = []) {
  const [questions, dispatch] = useImmerReducer(
    questionsReducer,
    initialQuestions,
    (initial) => initial.map((q, idx) => ({
      ...q,
      originalIndex: idx,
      isModified: false,
      isNew: false,
      id: q.id || `q-${idx}`,
    }))
  );

  // Memoizamos las funciones para evitar re-renders innecesarios
  const editQuestion = useCallback((id, text) => {
    dispatch({ type: 'EDIT_QUESTION', id, text });
  }, [dispatch]);

  const editOption = useCallback((questionId, optionIndex, text) => {
    dispatch({ type: 'EDIT_OPTION', questionId, optionIndex, text });
  }, [dispatch]);

  const duplicateQuestion = useCallback((id) => {
    dispatch({ type: 'DUPLICATE_QUESTION', id });
  }, [dispatch]);

  const deleteQuestion = useCallback((id) => {
    dispatch({ type: 'DELETE_QUESTION', id });
  }, [dispatch]);

  const replaceQuestion = useCallback((id, newQuestion) => {
    dispatch({ type: 'REPLACE_QUESTION', id, newQuestion });
  }, [dispatch]);

  const setLoading = useCallback((id, isLoading) => {
    dispatch({ type: 'SET_LOADING', id, isLoading });
  }, [dispatch]);

  const resetModifications = useCallback(() => {
    dispatch({ type: 'RESET_MODIFICATIONS' });
  }, [dispatch]);

  const hasUnsavedChanges = questions.some(q => q.isModified || q.isNew);

  return {
    questions,
    editQuestion,
    editOption,
    duplicateQuestion,
    deleteQuestion,
    replaceQuestion,
    setLoading,
    resetModifications,
    hasUnsavedChanges,
  };
}
