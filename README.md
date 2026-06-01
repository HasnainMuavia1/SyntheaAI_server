# 🪐 Synthea Backend (Django & Channels)

This is the secure backend server for Synthea, built with **Django REST Framework** and **Django Channels (ASGI)**. It handles AI agent workflows (powered by LangChain and Groq), database storage, workspace configurations, and real-time audio transcription streaming via websockets (using WhisperFlow).

---

## ⚡ Quick Start: Running with Docker Compose (Recommended)

Since the frontend and backend are structured as separate microservices, they communicate over a shared Docker network named `synthea-net`. Follow these steps to spin up the entire application:

### Step 1: Create the Shared Network (One-time Setup)
Run this command from your terminal to create the shared container network:
```bash
docker network create synthea-net
```

### Step 2: Build and Start the Backend
Navigate to `SyntheaAI_server/` and start the backend container:
```bash
docker compose up -d --build
```
*Note: The first build compiles PortAudio and downloads PyTorch (CPU). This will take a few minutes but runs completely automatically.*

### Step 3: Create an Admin / Superuser Account
To manage workspaces, users, and credentials, create a Django superuser:
```bash
docker exec -it synthea-backend python manage.py createsuperuser
```

### Step 4: Start the Frontend
Navigate to `SyntheaAI_client/` and start the Next.js container:
```bash
docker compose up -d --build
```
Access the application at 👉 **[http://localhost:3000](http://localhost:3000)** and log in using either the superuser credentials or by registering a new account.

---

## 🛠️ Local Development (Without Docker)

### Prerequisites
- Python 3.12+
- PortAudio development headers (required for `PyAudio` compilation):
  - **macOS**: `brew install portaudio`
  - **Ubuntu/Debian**: `sudo apt-get install portaudio19-dev`

### 1. Virtual Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Database Migrations
```bash
python manage.py migrate
```

### 4. Start the Daphne ASGI Server
```bash
python manage.py runserver
```

---

## 📂 Architecture and Layout Notes
- **Shared Workspaces**: On container boot, Django automatically checks and creates a `workspaces` directory sibling on your host. This holds user workspace files dynamically and syncs changes in real-time.
- **WhisperFlow**: The server includes an internal copy of the `whisperflow` voice streaming engine, running seamlessly on websocket endpoint `/ws/voice/`.
