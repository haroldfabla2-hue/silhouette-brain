#!/usr/bin/env python3
"""
Intelligent Entity Verification System
=====================================
Verifica entidades automáticamente usando:
1. Búsqueda en conversaciones
2. Análisis de patrones
3. Kimi/IA para verificación compleja
"""
import json
import os
import sys
sys.path.append(os.getenv('BRAIN_SRC_DIR', '/home/ubuntu/.openclaw/workspace/silhouette-brain/src/core'))
import re
from datetime import datetime
from collections import Counter

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', '/home/ubuntu/.openclaw/workspace/silhouette-brain/src'))

# Entidades CRÍTICAS que SIEMPRE deben estar verificadas
CRITICAL_ENTITIES = {
    'Alberto': {
        'type': 'person',
        'truth_patterns': [
            r'vegetariano',
            r'Brandistry',
            r'n8n',
            r'perú',
            r'peru',
            r'Lima',
            r'pizza',
            r'pastel de papa',
            r'Beto',
            r'Farah'
        ],
        'verified': False
    },
    'Brandistry': {
        'type': 'company',
        'truth_patterns': [
            r'Brandistry.*',
            r'Brandistry CRM',
            r'Brandistry.*automation',
            r'Brandistry.*n8n',
            r'NEXUS.*Brandistry',
            r'Brandistry automation',
            r'Brandistry workflow',
            r'Brandistry.*CRM',
            r'proyecto.*Brandistry'
        ],
        'verified': False
    },
    'Silhouette': {
        'type': 'agent',
        'truth_patterns': [
            r'Silhouette.*CEO',
            r'Silhouette.*coordin',
            r'Silhouette.*equipo',
            r'Silhouette.*agentes',
            r'coordin.*Silhouette',
            r'Silhouette.*memoria',
            r'Silhouette.*OpenClaw',
            r'Sil.*Cloud Office',
            r'Sil\.albertofarah\.com',
            r'Silhouette Agency OS',
            r'Silhouette.*Agencia',
            r'Sil.*inteligencia',
            r'Sil.*biomimetic',
            r'Sil.*artificial',
            r'Sil.*conciencia'
        ],
        'verified': False
    },
    'Roger': {
        'type': 'agent',
        'truth_patterns': [
            r'Roger.*scout',
            r'Roger.*oportunidades',
            r'Roger.*hunt',
            r'Roger.*freelance',
            r'Roger.*hunter'
        ],
        'verified': False
    },
    'Rick': {
        'type': 'agent',
        'truth_patterns': [
            r'Rick.*coder',
            r'Rick.*código',
            r'Rick.*developer',
            r'Rick.*code',
            r'Rick.*program',
            r'Rick.*GitHub'
        ],
        'verified': False
    },
    'Cami': {
        'type': 'agent',
        'truth_patterns': [
            r'Cami.*research',
            r'Cami.*investiga',
            r'Cami.*análisis',
            r'Cami.*investigar'
        ],
        'verified': False
    },
    'Rose': {
        'type': 'agent',
        'truth_patterns': [
            r'Rose.*analyst',
            r'Rose.*métricas',
            r'Rose.*análisis',
            r'Rose.*analytics'
        ],
        'verified': False
    },
    'Jack': {
        'type': 'agent',
        'truth_patterns': [
            r'Jack.*planner',
            r'Jack.*plan',
            r'Jack.*estrategia',
            r'Jack.*roadmap'
        ],
        'verified': False
    },
    'Larry': {
        'type': 'agent',
        'truth_patterns': [
            r'Larry.*social',
            r'Larry.*Twitter',
            r'Larry.*contenido',
            r'Larry.*LinkedIn',
            r'Larry.*post'
        ],
        'verified': False
    },
    'Flocky': {
        'type': 'agent',
        'truth_patterns': [
            r'Flocky.*GitHub',
            r'Flocky.*CI',
            r'Flocky.*repos',
            r'Flocky.*commit'
        ],
        'verified': False
    },
    'Nexus': {
        'type': 'project',
        'truth_patterns': [
            r'Nexus.*Brandistry',
            r'Nexus.*CRM',
            r'proyecto.*Nexus',
            r'Nexus.*automation',
            r'Nexus workflow'
        ],
        'verified': False
    },
    'Silhouette Agency OS': {
        'type': 'project',
        'truth_patterns': [
            r'Silhouette Agency OS',
            r'Agency OS.*open.*source',
            r'proyecto.*GitHub',
            r'github.*Silhouette',
            r'Silhouette.*asistente',
            r'Silhouette.*web',
            r'Silhouette.*biomimetica',
            r'Silhouette.*biomimetic',
            r'conciencia.*artificial',
            r'inteligencia.*artificial'
        ],
        'verified': False
    }
}

class EntityVerifier:
    """
    Sistema inteligente de verificación de entidades
    """
    
    def __init__(self):
        self.db_path = os.getenv('BRAIN_DATA_DIR', './data'/memory_core.db'
        self.results = []
    
    def get_all_entities(self):
        """Obtiene todas las entidades de la DB"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        cur = conn.cursor()
        cur.execute("SELECT * FROM entities ORDER BY mention_count DESC")
        rows = cur.fetchall()
        
        entities = []
        for row in rows:
            entities.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'mention_count': row[5],
                'verified': row[6],
                'truth': row[7]
            })
        
        conn.close()
        return entities
    
    def search_entity_context(self, entity_name, limit=20):
        """Busca menciones de una entidad en conversaciones"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        cur = conn.cursor()
        
        cur.execute("""
            SELECT message, speaker, timestamp 
            FROM conversations 
            WHERE message LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f'%{entity_name}%', limit))
        
        rows = cur.fetchall()
        results = []
        for row in rows:
            results.append({
                'message': row[0],
                'speaker': row[1],
                'timestamp': row[2]
            })
        
        conn.close()
        
        return results
    
    def verify_entity(self, entity_name, patterns):
        """
        Verifica una entidad buscando evidencia en conversaciones
        """
        print(f"   🔍 Verificando: {entity_name}")
        
        mentions = self.search_entity_context(entity_name)
        
        if not mentions:
            print(f"      ⚠️ Sin menciones")
            return {'verified': False, 'evidence': None, 'mentions': 0}
        
        # Buscar patrones de verdad
        evidence_found = []
        for mention in mentions:
            msg = mention['message'].lower()
            for pattern in patterns:
                if re.search(pattern.lower(), msg):
                    evidence_found.append(mention['message'][:100])
        
        # Verificar
        unique_evidence = list(set(evidence_found))[:3]  # Max 3 ejemplos
        
        is_verified = len(unique_evidence) >= 1
        
        result = {
            'entity': entity_name,
            'verified': is_verified,
            'evidence': unique_evidence,
            'mentions': len(mentions),
            'evidence_count': len(evidence_found)
        }
        
        if is_verified:
            truth = f"Verificado: {', '.join([e[:30] for e in unique_evidence[:2]])}..."
            result['truth'] = truth
            print(f"      ✅ VERIFICADO ({len(evidence_found)} evidencias)")
        else:
            print(f"      ⚠️ Sin evidencia suficiente ({len(mentions)} menciones)")
        
        return result
    
    def clean_noise_entities(self):
        """Limpia entidades que son ruido (palabras comunes)"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Palabras que son ruido
        noise_words = [
            'El', 'La', 'Los', 'Las', 'Un', 'Una', 'Unos', 'Unas',
            'De', 'Del', 'En', 'Con', 'Por', 'Para', 'Sin', 'Sobre',
            'Lo', 'Que', 'Qué', 'Se', 'Me', 'Te', 'Le', 'Nos', 'Os',
            'Solo', 'Solo', 'Todos', 'Todas', 'Otro', 'Otra', 'Otros', 'Otras',
            'Este', 'Esta', 'Estos', 'Estas', 'Ese', 'Esa', 'Esos', 'Esas',
            'Mi', 'Tu', 'Su', 'Mis', 'Tus', 'Sus', 'Nuestro', 'Nuestra',
            'Si', 'Sí', 'No', 'Ya', 'Aún', 'También', 'Pero', 'Porque',
            'Como', 'Cómo', 'Cuando', 'Cuándo', 'Dónde', 'Donde', 'Quién',
            'Test', 'Estado', 'Permanent', 'Curiosity', 'Ambos', 'System'
        ]
        
        # Contar entidades de ruido
        cur.execute("SELECT name, mention_count FROM entities WHERE LOWER(name) IN (" + 
                   ','.join(['?' for _ in noise_words]) + ")", noise_words)
        noise_entities = cur.fetchall()
        
        print(f"\n🧹 Limpiando {len(noise_entities)} entidades de ruido...")
        
        deleted = 0
        for name, count in noise_entities:
            if count < 10:  # Solo borrar si tiene pocas menciones
                cur.execute("DELETE FROM entities WHERE name = ?", (name,))
                deleted += 1
                print(f"   ❌ Eliminado: {name} ({count} menciones)")
        
        conn.commit()
        conn.close()
        
        print(f"   ✅ Eliminados: {deleted}")
        return deleted
    
    def verify_all_critical(self):
        """Verifica todas las entidades críticas"""
        print("\n" + "="*50)
        print("🛡️ VERIFICACIÓN INTELIGENTE DE ENTIDADES")
        print("="*50)
        
        entities = self.get_all_entities()
        entity_map = {e['name']: e for e in entities}
        
        verified_count = 0
        new_verifications = []
        
        for entity_name, config in CRITICAL_ENTITIES.items():
            # Buscar en DB
            db_entity = entity_map.get(entity_name)
            
            if not db_entity:
                print(f"\n   ⚠️ {entity_name} NO existe en DB")
                continue
            
            # Verificar
            result = self.verify_entity(entity_name, config['truth_patterns'])
            
            if result['verified'] and not db_entity.get('verified'):
                # Actualizar en DB
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                
                cur.execute("""
                    UPDATE entities 
                    SET verified = 1, truth = ?, mention_count = mention_count + 1
                    WHERE name = ?
                """, (result['truth'], entity_name))
                
                conn.commit()
                conn.close()
                
                verified_count += 1
                new_verifications.append(entity_name)
                print(f"      💾 GUARDADO en DB")
            
            self.results.append(result)
        
        print("\n" + "="*50)
        print(f"✅ VERIFICACIÓN COMPLETADA")
        print(f"   Nuevas verificaciones: {verified_count}")
        print(f"   Entidades críticas: {len(CRITICAL_ENTITIES)}")
        print("="*50)
        
        return {
            'verified': verified_count,
            'new_verifications': new_verifications,
            'total_critical': len(CRITICAL_ENTITIES)
        }
    
    def run_full_verification(self):
        """Ejecuta verificación completa"""
        print("\n🚀 INICIANDO VERIFICACIÓN COMPLETA...")
        
        # 1. Verificar entidades críticas
        result = self.verify_all_critical()
        
        # 2. Limpiar ruido
        deleted = self.clean_noise_entities()
        
        # 3. Resumen final
        print("\n" + "="*50)
        print("📊 RESUMEN FINAL")
        print("="*50)
        
        for r in self.results:
            status = "✅" if r['verified'] else "⚠️"
            print(f"   {status} {r['entity']}: {r.get('mentions', 0)} menciones")
        
        return result

if __name__ == "__main__":
    verifier = EntityVerifier()
    verifier.run_full_verification()
