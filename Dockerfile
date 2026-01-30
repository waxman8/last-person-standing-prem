FROM python:3.11-slim

# Install sqlite3 for manual data editing
RUN apt-get update && apt-get install -y sqlite3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists for SQLite and declare it as a volume for persistence
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Default API key (empty, to be provided at runtime)
ENV FOOTBALL_DATA_API_KEY=""
ENV DATABASE_URL="sqlite:////app/data/lms.db"

# Expose port
EXPOSE 8000

# Initialize admin and start app
CMD python init_admin.py && uvicorn main:app --host 0.0.0.0 --port 8000
