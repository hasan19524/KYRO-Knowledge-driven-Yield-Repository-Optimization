# KYRO Backend

FastAPI backend for the KYRO project.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running

```bash
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

## Endpoints

- `GET /health` - Health check endpoint
