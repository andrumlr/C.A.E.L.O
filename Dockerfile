FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt ./backend/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the rest of the project (including prompts/, backend/, etc.)
COPY . .

# Railway provides the PORT environment variable
EXPOSE 8080

# Start the app from the backend directory
CMD cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
