FROM python:3.9-slim-bullseye

ENV PYTHONUNBUFFERED=1 

WORKDIR /app

# Install AI Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Code
COPY . .

# Expose port
EXPOSE 8001

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]