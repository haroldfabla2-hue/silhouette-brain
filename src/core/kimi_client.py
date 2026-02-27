#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Kimi k2.5 Integration for Agents
Uses OpenClaw's configured Kimi API
"""
import requests
import json
import os

# Get API key from OpenClaw config
KIMI_API_KEY = "sk-kimi-1TwqVcohVActjxEVPuzkGDRuuaxo687BLWM6h4vgAo650kAVU6NHc6u4FSgvIt9d"
KIMI_BASE_URL = "https://api.moonshot.cn/v1"

def kimi_chat(prompt: str, model: str = "kimi-k2.5", temperature: float = 0.7) -> str:
    """Send prompt to Kimi k2.5 and get response"""
    
    response = requests.post(
        f"{KIMI_BASE_URL}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KIMI_API_KEY}"
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un asistente útil."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 4096
        }
    )
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Kimi error: {response.status_code} - {response.text}")

def kimi_analyze(text: str, analysis_type: str = "general") -> str:
    """Use Kimi for analysis tasks"""
    
    prompts = {
        "general": f"Analiza el siguiente texto y dame los puntos clave:\n\n{text}",
        "sentiment": f"Analiza el sentimiento del siguiente texto:\n\n{text}",
        "topics": f"Extrae los temas principales del siguiente texto:\n\n{text}",
        "summary": f"Resume el siguiente texto de manera clara:\n\n{text}",
        "entities": f"Extrae las entidades mencionadas (personas, empresas, tecnologías):\n\n{text}",
    }
    
    prompt = prompts.get(analysis_type, prompts["general"])
    return kimi_chat(prompt)

def kimi_write(topic: str, style: str = "professional", platform: str = "twitter") -> str:
    """Use Kimi for writing tasks"""
    
    styles = {
        "professional": "Escribe de manera profesional y clara",
        "casual": "Escribe de manera casual y amigable",
        "technical": "Escribe de manera técnica pero accesible",
        "persuasive": "Escribe de manera persuasiva",
        "viral": "Escribe de manera que sea viral y pegajoso"
    }
    
    platforms = {
        "twitter": "Máximo 280 caracteres, directo, con emoji opcional",
        "linkedin": "Profesional, más largo, formato LinkedIn",
        "youtube": "Título atractivo, descripción detallada"
    }
    
    prompt = f"{styles.get(style, styles['professional'])}. Plataforma: {platforms.get(platform, platforms['twitter'])}. Tema: {topic}"
    return kimi_chat(prompt)

# Test
if __name__ == "__main__":
    print("Testing Kimi k2.5...")
    
    # Test 1: Simple chat
    result = kimi_chat("Hola, dime qué puedes hacer")
    print(f"Chat: {result[:200]}...")
    
    # Test 2: Analysis
    result = kimi_analyze("AI is transforming the world. Machine learning is advancing rapidly.", "summary")
    print(f"Analysis: {result[:200]}...")
    
    # Test 3: Writing
    result = kimi_write("Inteligencia Artificial", style="casual", platform="twitter")
    print(f"Writing: {result[:200]}...")
    
    print("\n✅ Kimi working!")
