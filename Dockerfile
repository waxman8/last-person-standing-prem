FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists for SQLite
RUN mkdir -p /app/data

# Default API key (empty, to be provided at runtime)
ENV FOOTBALL_DATA_API_KEY=""
ENV DATABASE_URL="sqlite:////app/data/lms.db"

# Expose port
EXPOSE 8000

# Initialize admin and start app
CMD python init_admin.py && uvicorn main:app --host 0.0.0.0 --port 8000
