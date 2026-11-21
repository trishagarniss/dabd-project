FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000 9001
CMD ["python", "-m", "uvicorn", "src.serving.api:app", "--host", "0.0.0.0", "--port", "8000"]
