"""One-time migration: preserve local DB access without printing credentials."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = ROOT / "src/configuration/config.py"
source = config.read_text(encoding="utf-8")
values = {}
for statement in ast.parse(source).body:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
        try:
            values[statement.targets[0].id] = ast.literal_eval(statement.value)
        except (ValueError, TypeError):
            pass
if not isinstance(values.get('MYSQL_CONFIG'), dict):
    print('Configuration already uses environment variables; nothing changed.')
    raise SystemExit(0)
mysql, neo = values.get("MYSQL_CONFIG", {}), values.get("NEO4J_CONFIG", {})
credentials = {"MYSQL_HOST": mysql.get("host"), "MYSQL_PORT": mysql.get("port"), "MYSQL_USER": mysql.get("user"), "MYSQL_PASSWORD": mysql.get("password"), "MYSQL_DATABASE": mysql.get("database"), "NEO4J_URI": neo.get("uri"), "NEO4J_USERNAME": neo.get("auth", [None,None])[0], "NEO4J_PASSWORD": neo.get("auth", [None,None])[1]}
env = ROOT / ".env"
text = env.read_text(encoding="utf-8") if env.exists() else ""
for key, value in credentials.items():
    if value is not None and not re.search(rf"^{key}=", text, re.M):
        text += f"\n{key}={value}"
if not re.search(r"^AI_MODE=", text, re.M):
    text += "\nAI_MODE=local"
env.write_text(text.rstrip()+"\n", encoding="utf-8")
source = source.replace("from pathlib import Path", "import os\nfrom pathlib import Path\nfrom dotenv import load_dotenv")
source = source.replace("from absl.logging import LOG_DIR", "load_dotenv(Path(__file__).resolve().parents[2] / '.env')")
start = source.index("MYSQL_CONFIG =")
source = source[:start] + '''MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "gmall"),
    "connect_timeout": 5,
}
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687"),
    "auth": (os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "")),
}
NEO4J_READ_CONFIG = {
    "uri": NEO4J_CONFIG["uri"],
    "auth": (os.getenv("NEO4J_READ_USERNAME", ""), os.getenv("NEO4J_READ_PASSWORD", "")),
}
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
'''
config.write_text(source, encoding="utf-8")
print("Local database settings migrated; no credential values printed.")
