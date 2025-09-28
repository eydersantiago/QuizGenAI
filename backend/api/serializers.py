# # api/serializers.py
# from rest_framework import serializers

# TAXONOMY = [
#     "algoritmos", "redes", "bd", "bases de datos",
#     "sistemas operativos", "poo", "ciberseguridad",
#     "ia básica", "arquitectura", "estructura de datos",
#     "complejidad computacional", "np-completitud",
#     "teoría de la computación", "autómatas y gramáticas"
# ]

# DIFFICULTY_CHOICES = ["Fácil", "Media", "Difícil"]
# TYPE_CHOICES = ["mcq", "vf", "short"]

# class RegenerateRequestSerializer(serializers.Serializer):
#     session_id = serializers.CharField()
#     index = serializers.IntegerField(min_value=0)
#     type = serializers.ChoiceField(choices=TYPE_CHOICES)
#     topic = serializers.CharField(required=False, allow_blank=False)
#     difficulty = serializers.ChoiceField(choices=DIFFICULTY_CHOICES, required=False)
#     debug = serializers.BooleanField(required=False, default=False)

#     def validate_topic(self, value):
#         v = value.strip().lower()
#         if v not in [t.lower() for t in TAXONOMY]:
#             raise serializers.ValidationError(
#                 "El tema no está en la taxonomía permitida (HU-06)."
#             )
#         return value

# class QuestionSerializer(serializers.Serializer):
#     type = serializers.ChoiceField(choices=TYPE_CHOICES)
#     question = serializers.CharField()
#     answer = serializers.CharField(required=False, allow_blank=True)
#     options = serializers.ListField(
#         child=serializers.CharField(), required=False, allow_empty=True
#     )
#     explanation = serializers.CharField(required=False, allow_blank=True)

#     def validate(self, data):
#         t = data.get("type")
#         if t == "mcq":
#             if "options" not in data or not isinstance(data["options"], list) or len(data["options"]) < 3:
#                 raise serializers.ValidationError("MCQ requiere al menos 3 opciones.")
#             if "answer" not in data:
#                 raise serializers.ValidationError("MCQ requiere campo 'answer' (A/B/C/D).")
#         if t == "vf":
#             # answer esperado: "Verdadero" o "Falso"
#             ans = (data.get("answer") or "").strip().lower()
#             if ans not in ["verdadero", "falso"]:
#                 raise serializers.ValidationError("VF requiere answer = 'Verdadero' o 'Falso'.")
#         # short: opcionalmente puede traer 'answer' y 'explanation'
#         return data
