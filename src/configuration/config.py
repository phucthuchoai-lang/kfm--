import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

#1.目录路径
ROOT_DIR = Path(__file__).parent.parent.parent

DATA_DIR = ROOT_DIR / 'data'
NER_DIR = 'ner'
RAW_DATA_DIR = DATA_DIR / NER_DIR / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / NER_DIR / 'processed'

LOG_DIR = ROOT_DIR / 'logs'
CHECKPOINT_DIR = ROOT_DIR / 'checkpoints'

# web静态目录
WEB_STATIC_DIR = ROOT_DIR / 'src' / 'web' / 'static'

#2.数据文件名和模型名称
RAW_DATA_FILE = str(RAW_DATA_DIR/'data.json')
MODEL_NAME = 'google-bert/bert-base-chinese'

#3.超参数
BATCH_SIZE = 2
EPOCHS = 5
LEARNING_RATE = 1e-5
SAVE_STEPS = 20

# 4.任务分类标签
LABELS =['B','I','O']

# 5. 数据库连接
MYSQL_CONFIG = {
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
