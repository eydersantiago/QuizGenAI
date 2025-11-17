from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
import uuid

from .models import SavedQuiz


class ToggleFavoriteQuestionTests(APITestCase):
    """Tests para el endpoint de marcar/desmarcar preguntas favoritas"""

    def setUp(self):
        """Configuración inicial para cada test"""
        # Crear un quiz de prueba
        self.quiz = SavedQuiz.objects.create(
            title="Quiz de Prueba",
            topic="Python",
            difficulty="Media",
            types=["mcq", "vf"],
            counts={"mcq": 3, "vf": 2},
            questions=[
                {"type": "mcq", "question": "¿Qué es Python?", "options": ["A", "B", "C", "D"], "correct": "A"},
                {"type": "vf", "question": "Python es un lenguaje compilado", "correct": False},
                {"type": "mcq", "question": "¿Qué es una lista?", "options": ["A", "B", "C", "D"], "correct": "B"},
                {"type": "mcq", "question": "¿Qué es un diccionario?", "options": ["A", "B", "C", "D"], "correct": "C"},
                {"type": "vf", "question": "Python usa tipado dinámico", "correct": True},
            ],
            user_answers={},
            current_question=0,
            favorite_questions=[]
        )
        self.url = reverse('saved_quiz_toggle_mark', kwargs={'quiz_id': self.quiz.id})

    def test_mark_question_as_favorite(self):
        """Test: marcar una pregunta como favorita"""
        response = self.client.patch(self.url, {'question_index': 0}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['is_favorite'])
        self.assertIn(0, response.json()['favorite_questions'])
        self.assertEqual(response.json()['question_index'], 0)

        # Verificar en la base de datos
        self.quiz.refresh_from_db()
        self.assertIn(0, self.quiz.favorite_questions)

    def test_unmark_favorite_question(self):
        """Test: desmarcar una pregunta que ya era favorita"""
        # Primero marcamos la pregunta
        self.quiz.favorite_questions = [0, 2]
        self.quiz.save()

        # Ahora desmarcamos
        response = self.client.patch(self.url, {'question_index': 0}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()['is_favorite'])
        self.assertNotIn(0, response.json()['favorite_questions'])
        self.assertIn(2, response.json()['favorite_questions'])

        # Verificar en la base de datos
        self.quiz.refresh_from_db()
        self.assertNotIn(0, self.quiz.favorite_questions)
        self.assertIn(2, self.quiz.favorite_questions)

    def test_toggle_multiple_questions(self):
        """Test: marcar múltiples preguntas como favoritas"""
        # Marcar pregunta 0
        response1 = self.client.patch(self.url, {'question_index': 0}, format='json')
        self.assertTrue(response1.json()['is_favorite'])

        # Marcar pregunta 2
        response2 = self.client.patch(self.url, {'question_index': 2}, format='json')
        self.assertTrue(response2.json()['is_favorite'])

        # Marcar pregunta 4
        response3 = self.client.patch(self.url, {'question_index': 4}, format='json')
        self.assertTrue(response3.json()['is_favorite'])

        # Verificar que todas están marcadas
        self.quiz.refresh_from_db()
        self.assertEqual(len(self.quiz.favorite_questions), 3)
        self.assertIn(0, self.quiz.favorite_questions)
        self.assertIn(2, self.quiz.favorite_questions)
        self.assertIn(4, self.quiz.favorite_questions)

    def test_quiz_not_found(self):
        """Test: intentar marcar favorita en un quiz que no existe"""
        invalid_url = reverse('saved_quiz_toggle_mark', kwargs={'quiz_id': uuid.uuid4()})
        response = self.client.patch(invalid_url, {'question_index': 0}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_question_index(self):
        """Test: no enviar el índice de la pregunta"""
        response = self.client.patch(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('question_index', response.json()['error'].lower())

    def test_invalid_question_index_type(self):
        """Test: enviar un índice con tipo inválido"""
        response = self.client.patch(self.url, {'question_index': 'invalid'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_negative_question_index(self):
        """Test: enviar un índice negativo"""
        response = self.client.patch(self.url, {'question_index': -1}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('inválido', response.json()['error'].lower())

    def test_question_index_out_of_range(self):
        """Test: enviar un índice fuera de rango"""
        response = self.client.patch(self.url, {'question_index': 10}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('inválido', response.json()['error'].lower())

    def test_handle_null_favorite_questions(self):
        """Test: manejar el caso donde favorite_questions es None"""
        # Establecer favorite_questions como None
        self.quiz.favorite_questions = None
        self.quiz.save()

        response = self.client.patch(self.url, {'question_index': 0}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['is_favorite'])
        self.assertIn(0, response.json()['favorite_questions'])

        # Verificar que se inicializó correctamente
        self.quiz.refresh_from_db()
        self.assertIsNotNone(self.quiz.favorite_questions)
        self.assertIn(0, self.quiz.favorite_questions)

    def test_only_updates_favorite_questions_field(self):
        """Test: verificar que solo se actualiza el campo favorite_questions"""
        original_current_question = self.quiz.current_question
        original_user_answers = self.quiz.user_answers.copy()

        response = self.client.patch(self.url, {'question_index': 0}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar que otros campos no cambiaron
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.current_question, original_current_question)
        self.assertEqual(self.quiz.user_answers, original_user_answers)


class GenerateReviewQuizTests(APITestCase):
    """Tests para el endpoint de generar quiz de repaso con preguntas favoritas"""

    def setUp(self):
        """Configuración inicial para cada test"""
        # Crear un quiz de prueba con preguntas favoritas
        self.quiz = SavedQuiz.objects.create(
            title="Quiz de Python",
            topic="Python",
            category="lenguajes de programación",
            difficulty="Media",
            types=["mcq", "vf"],
            counts={"mcq": 3, "vf": 2},
            questions=[
                {
                    "type": "mcq",
                    "question": "¿Qué es una lista en Python?",
                    "options": ["A) Estructura mutable", "B) Estructura inmutable", "C) Solo números", "D) Solo strings"],
                    "answer": "A",
                    "explanation": "Las listas son mutables"
                },
                {
                    "type": "vf",
                    "question": "Python es un lenguaje compilado",
                    "answer": "Falso",
                    "explanation": "Python es interpretado"
                },
                {
                    "type": "mcq",
                    "question": "¿Qué es un diccionario?",
                    "options": ["A) Estructura clave-valor", "B) Lista ordenada", "C) Tupla", "D) Set"],
                    "answer": "A",
                    "explanation": "Los diccionarios almacenan pares clave-valor"
                },
            ],
            user_answers={},
            current_question=0,
            favorite_questions=[0, 2]  # Primera y tercera pregunta marcadas
        )
        self.url = reverse('saved_quiz_create_review', kwargs={'quiz_id': self.quiz.id})

    def test_quiz_not_found(self):
        """Test: intentar generar repaso de un quiz que no existe"""
        invalid_url = reverse('saved_quiz_create_review', kwargs={'quiz_id': uuid.uuid4()})
        response = self.client.post(invalid_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_favorite_questions(self):
        """Test: quiz sin preguntas favoritas marcadas"""
        self.quiz.favorite_questions = []
        self.quiz.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('favoritas', response.json()['message'].lower())

    def test_favorite_questions_is_none(self):
        """Test: campo favorite_questions es None"""
        self.quiz.favorite_questions = None
        self.quiz.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_empty_questions_list(self):
        """Test: quiz sin preguntas válidas"""
        self.quiz.questions = []
        self.quiz.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_invalid_favorite_indices(self):
        """Test: índices de favoritas fuera de rango"""
        self.quiz.favorite_questions = [10, 20, 30]  # Índices que no existen
        self.quiz.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('inválidos', response.json()['message'].lower())

    def test_mixed_valid_invalid_indices(self):
        """Test: algunos índices válidos y otros inválidos (debe procesar solo los válidos)"""
        # Este test verificaría el comportamiento cuando hay índices mezclados
        # pero depende de si los proveedores LLM están disponibles
        self.quiz.favorite_questions = [0, 10, 2]  # 0 y 2 válidos, 10 inválido
        self.quiz.save()

        # No podemos garantizar que la generación funcione sin API keys
        # pero sí podemos verificar que no falle por validación
        response = self.client.post(self.url)

        # Puede ser 201 (éxito), 503 (sin créditos), o 500 (error en generación)
        # Lo importante es que no sea 400 por validación
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ])

    def test_response_structure_on_error(self):
        """Test: estructura de respuesta cuando no hay favoritas"""
        self.quiz.favorite_questions = []
        self.quiz.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        json_data = response.json()
        self.assertIn('error', json_data)
        self.assertIn('message', json_data)
