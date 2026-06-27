#!/bin/bash
# Silhouette Brain - AI Auto-Installation Script
# Este script está diseñado para ser ejecutado por un Agente de IA con acceso a terminal.

echo "🧠 Iniciando instalación automática de Silhouette Brain..."

# 1. Clonar el repositorio si no estamos dentro de él
if [ ! -f "docker-compose.yml" ]; then
    echo "📥 Clonando repositorio..."
    git clone https://github.com/haroldfabla2-hue/silhouette-brain.git
    cd silhouette-brain
fi

# 2. Preparar el entorno
if [ ! -f ".env" ]; then
    echo "📄 Creando archivo .env desde la plantilla..."
    cp .env.example .env
    echo "⚠️ ATENCIÓN HUMANO: Edita el archivo .env y define:"
    echo "    - NEO4J_PASSWORD (obligatorio)"
    echo "    - REASONING_API_KEY (opcional, para la síntesis/razonamiento)"
    echo "    Los embeddings son 100% locales (fastembed) y no requieren clave."
fi

# 3. Intentar levantar los servicios (Docker)
echo "🐳 Levantando infraestructura (Docker)..."
if command -v docker-compose >/dev/null 2>&1; then
    docker-compose up -d
elif docker --help >/dev/null 2>&1; then
    docker compose up -d
else
    echo "❌ Docker no detectado. Por favor, instala Docker para continuar."
    exit 1
fi

# 4. Ejecutar la integración cognitiva con el Agente
echo "🧬 Integrando el cerebro con el sistema de archivos del agente..."
python3 src/core/agent_self_configure.py

echo "✅ Instalación y configuración completada."
echo "💡 PRÓXIMO PASO: Verifica que NEO4J_PASSWORD (y, si la usas, REASONING_API_KEY) estén definidas en .env."
