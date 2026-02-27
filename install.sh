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
    echo "⚠️ ATENCIÓN HUMANO: Por favor, introduce tu OPENAI_API_KEY en el archivo .env para habilitar los embeddings."
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
echo "💡 PRÓXIMO PASO: El humano debe asegurarse de que la OPENAI_API_KEY en el .env sea válida."
