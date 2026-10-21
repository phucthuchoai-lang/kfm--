from pathlib import Path

from absl.logging import LOG_DIR

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
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gmall',
}

NEO4J_CONFIG = {
    'uri': "neo4j://localhost:7687",
    'auth': ("neo4j", "12345678")
}

API_KEY = 'sk-025eb50a6eb44c709c5c078190353383'