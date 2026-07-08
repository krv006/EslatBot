FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Xavfsizlik: konteyner root emas, oddiy user sifatida ishlaydi
RUN useradd --create-home appuser \
    && mkdir -p /app/data /app/root/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

# Standart buyruq — bot. Adminka compose'da o'z buyrug'i bilan ishga tushadi.
CMD ["python", "main.py"]
