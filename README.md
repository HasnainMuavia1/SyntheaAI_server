# Synthea Backend

This directory contains the Django backend for the Synthea project.

## Prerequisites

- Python 3.10+
- Virtual environment (recommended)

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Servers

### 1. Django API Server
Run the main Django development server for API and task management:
```bash
python manage.py runserver
```

### 2. Whisper Fast Server
Run the FastAPI-based Whisper server for real-time transcription. This server is located in the `whisper-flow` directory but should be run using the project's Python environment.
```bash
python whisper-flow/whisperflow/fast_server.py
```

## Database Migrations
To apply migrations or create new ones:
```bash
python manage.py makemigrations
python manage.py migrate
```
