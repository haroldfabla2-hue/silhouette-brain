import os
import glob
import re

src_dir = '/root/silhouette-brain/src'
files = glob.glob(f"{src_dir}/**/*.py", recursive=True)

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Reemplazar rutas absolutas a una estructura relativa o env var
    content = content.replace("'/root/.openclaw/skills/silhouette-memory/scripts'", "os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__)))")
    content = content.replace("'/root/.openclaw/skills/silhouette-memory/data", "os.getenv('BRAIN_DATA_DIR', './data'")
    content = content.replace('"/root/.openclaw/skills/silhouette-memory/data', 'os.getenv("BRAIN_DATA_DIR", "./data"')
    content = content.replace('/root/.openclaw/skills/silhouette-memory/data', './data')
    
    # Reemplazar credenciales comunes de Neo4j (si existen explícitamente)
    content = re.sub(r'NEO4J_PASSWORD\s*=\s*["\']openclaw123["\']', 'NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")', content)
    content = re.sub(r'NEO4J_URI\s*=\s*["\']bolt://localhost:17687["\']', 'NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")', content)
    
    # Ocultar OpenAI API Key
    content = re.sub(r'api_key\s*=\s*["\']sk-proj-[a-zA-Z0-9_-]+["\']', 'api_key = os.getenv("OPENAI_API_KEY")', content)
    content = re.sub(r'["\']sk-proj-[a-zA-Z0-9_-]+["\']', 'os.getenv("OPENAI_API_KEY")', content)

    # Añadir import os si se usó os.getenv pero no estaba importado
    if 'os.getenv' in content and 'import os' not in content:
        content = 'import os\n' + content

    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)

print("Sanitización completada.")
