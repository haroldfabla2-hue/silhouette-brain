import os
#!/usr/bin/env python3
"""
Silhouette AI Analysis Tool
Usa Kimi y OpenAI para análisis inteligente
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

from kimi_client import kimi_analyze, kimi_write
from memory_core import get_memory_core

def analyze_my_responses():
    """Analiza mis últimas respuestas para mejorar"""
    core = get_memory_core()
    
    # Obtener mis últimas respuestas
    cur = core.conn.cursor()
    cur.execute("""
        SELECT message FROM conversations 
        WHERE speaker = 'assistant' 
        ORDER BY timestamp DESC 
        LIMIT 20
    """)
    
    responses = [row[0] for row in cur.fetchall()]
    
    if not responses:
        print("No hay respuestas para analizar")
        return
    
    # Unir las respuestas
    combined = "\n\n".join(responses[:10])
    
    # Analizar con Kimi
    print("🤖 Analizando respuestas con Kimi...")
    analysis = kimi_analyze(
        f"Analiza estas respuestas de un asistente de IA y dame:\n"
        f"1. Fortalezas (qué hace bien)\n"
        f"2. Áreas de mejora\n"
        f"3. Patrones de comportamiento\n"
        f"4. Sugerencias específicas\n\n"
        f"Respuestas:\n{combined[:3000]}",
        "general"
    )
    
    print("\n📊 ANÁLISIS:")
    print(analysis)
    
    return analysis

def improve_context():
    """Usa Kimi para mejorar cómo obtengo contexto"""
    print("🔍 Mejorando sistema de contexto...")
    
    # Analizar qué tipo de queries tengo
    core = get_memory_core()
    cur = core.conn.cursor()
    cur.execute("""
        SELECT message FROM conversations 
        WHERE speaker = 'user' 
        ORDER BY timestamp DESC 
        LIMIT 50
    """)
    
    queries = [row[0] for row in cur.fetchall()]
    
    combined = "\n".join(queries[:20])
    
    improvement = kimi_analyze(
        f"Dado estas preguntas que hace un usuario a una IA:\n{combined}\n\n"
        f"Qué palabras clave o patrones debería buscar en la memoria "
        f"para dar mejores respuestas? Dame una lista de términos.",
        "topics"
    )
    
    print("\n💡 MEJORAS SUGERIDAS:")
    print(improvement)
    
    return improvement

def generate_daily_insight():
    """Genera un insight diario usando Kimi"""
    print("💭 Generando insight diario...")
    
    core = get_memory_core()
    cur = core.conn.cursor()
    
    # Obtener temas recientes
    cur.execute("""
        SELECT message FROM conversations 
        WHERE timestamp > strftime('%s', 'now') - 86400
        ORDER BY timestamp DESC
        LIMIT 30
    """)
    
    messages = [row[0] for row in cur.fetchall()]
    
    if not messages:
        print("No hay mensajes recientes")
        return
    
    combined = "\n".join(messages[:15])
    
    insight = kimi_analyze(
        f"Basado en esta conversación reciente del usuario:\n{combined}\n\n"
        f"Dame un insight útil sobre qué debería recordar o en qué debería enfocarse.",
        "summary"
    )
    
    print("\n💡 INSIGHT DEL DÍA:")
    print(insight)
    
    return insight

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Silhouette AI Analysis")
    parser.add_argument("--analyze", action="store_true", help="Analizar mis respuestas")
    parser.add_argument("--improve", action="store_true", help="Mejorar contexto")
    parser.add_argument("--insight", action="store_true", help="Generar insight diario")
    
    args = parser.parse_args()
    
    if args.analyze:
        analyze_my_responses()
    elif args.improve:
        improve_context()
    elif args.insight:
        generate_daily_insight()
    else:
        print("Usa: --analyze, --improve, o --insight")
