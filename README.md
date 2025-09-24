# QuizGenAI

QuizGenAI es una aplicación web para la generación y gestión de quizzes utilizando inteligencia artificial. El proyecto está dividido en dos partes principales: un backend construido con Django y Django REST Framework, y un frontend desarrollado con React.

## Estructura del Proyecto

```
QuizGenAI/
│
├── backend/      # API y lógica del servidor (Django + DRF)
│   ├── api/      # App principal de Django
│   ├── backend/  # Configuración del proyecto Django
│   ├── db.sqlite3
│   ├── manage.py
│   └── package.json
│
├── frontend/     # Interfaz de usuario (React)
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── README.md
│
├── requirements.txt
└── README.md
```

## Tecnologías Utilizadas

- **Backend:** Django, Django REST Framework, SQLite
- **Frontend:** React, Create React App

## Instalación

### Backend

1. Instala las dependencias de Python:
	```bash
	pip install -r requirements.txt
	```
2. Aplica migraciones:
	```bash
	cd backend
	python manage.py migrate
	```
3. Inicia el servidor de desarrollo:
	```bash
	python manage.py runserver
	```

### Frontend

1. Instala las dependencias de Node.js:
	```bash
	cd frontend
	npm install
	```
2. Inicia la aplicación React:
	```bash
	npm start
	```

## Scripts Útiles

- **Backend:**  
  - `python manage.py runserver` — Inicia el servidor Django.
  - `python manage.py migrate` — Aplica migraciones de la base de datos.

- **Frontend:**  
  - `npm start` — Inicia la app en modo desarrollo.
  - `npm run build` — Compila la app para producción.
  - `npm test` — Ejecuta los tests.

## Contribución

1. Haz un fork del repositorio.
2. Crea una rama para tu feature (`git checkout -b feature/nueva-funcionalidad`).
3. Realiza tus cambios y haz commit.
4. Haz push a tu rama y abre un Pull Request.

## Licencia

Este proyecto está bajo la licencia MIT.
