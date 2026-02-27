FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema y de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY src/ ./src/
COPY data/ ./data/

# Variables de entorno por defecto
ENV PYTHONPATH=/app/src
ENV BRAIN_DATA_DIR=/app/data

# Exponer el puerto de la Brain API
EXPOSE 9876

# Comando por defecto: Ejecutar la API del cerebro
CMD ["python", "src/api/enhanced_memory_api.py"]