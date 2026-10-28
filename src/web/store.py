"""Transactional local persistence for the explicitly labelled demo platform."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def pack(value):
    return json.dumps(value, ensure_ascii=False)


PRODUCTS = [
    ("p1", "小米 15", "小米", "手机", 3999, "轻巧旗舰，日常与影像兼顾", "phone", "#b8d7c8", {"内存": "12GB + 256GB", "屏幕": "6.36 英寸", "电池": "5400mAh", "重量": "191g", "特点": "小屏 / 长续航"}),
    ("p2", "华为 Pura 70", "华为", "手机", 4999, "记录生活的每一个动人瞬间", "phone", "#e0c8d0", {"内存": "12GB + 256GB", "屏幕": "6.6 英寸", "电池": "4900mAh", "重量": "207g", "特点": "影像 / 人像"}),
    ("p3", "iPhone 16", "Apple", "手机", 5999, "流畅体验，轻松融入你的工作生活", "phone", "#c8cef1", {"内存": "128GB 存储", "屏幕": "6.1 英寸", "电池": None, "重量": "170g", "特点": "iOS 生态 / 轻便"}),
    ("p4", "Redmi Buds 6", "小米", "耳机", 199, "把城市的声音，调成自己的节奏", "buds", "#d5e8bc", {"连接": "蓝牙", "降噪": "主动降噪", "续航": "总续航约 42 小时", "防护": "IP54", "特点": "通勤 / 性价比"}),
    ("p5", "FreeBuds 6i", "华为", "耳机", 499, "喧闹之外，留一点空间给音乐", "buds", "#d8d0eb", {"连接": "蓝牙", "降噪": "主动降噪", "续航": "总续航约 35 小时", "防护": "IP54", "特点": "通勤 / 降噪"}),
    ("p6", "AirPods 4", "Apple", "耳机", 999, "轻轻戴上，随心听见", "buds", "#e7dcc8", {"连接": "蓝牙", "降噪": "此演示款不支持", "续航": "总续航约 30 小时", "防护": "IP54", "特点": "iOS 生态 / 开放式"}),
    ("p7", "米家便携咖啡机", "米家", "生活", 399, "让一杯好咖啡，成为日常", "coffee", "#d7bba2", {"容量": "300mL", "供电": "插电", "重量": "1.2kg", "特点": "办公 / 咖啡"}),
    ("p8", "轻旅双肩包", "Morrow", "出行", 269, "轻装出发，装下你的周末计划", "bag", "#cbd3be", {"容量": "20L", "材质": "再生聚酯纤维", "重量": "560g", "特点": "通勤 / 短途出行"}),
    ("p9", "桌面氛围台灯", "米家", "生活", 179, "一束柔和的光，陪你专注", "lamp", "#ead9b4", {"功率": "9W", "色温": "2700–6500K", "控制": "触控调光", "特点": "阅读 / 办公"}),
    ("p10", "WATCH FIT 3", "华为", "手表", 799, "把运动和生活，戴在腕间", "watch", "#d9dfe5", {"屏幕": "1.82 英寸", "续航": "典型场景约 7 天", "防护": "5ATM", "特点": "运动 / 消息提醒"}),
    ("p11", "Xiaomi Watch S4", "小米", "手表", 999, "每一段路，都有新的节奏", "watch", "#c1d8d3", {"屏幕": "1.43 英寸", "续航": "典型场景约 15 天", "防护": "5ATM", "特点": "运动 / 圆形表盘"}),
    ("p12", "城市随行保温杯", "Morrow", "出行", 129, "温度刚好，陪你走远一点", "bottle", "#d6c9b8", {"容量": "450mL", "材质": "不锈钢", "重量": "280g", "特点": "通勤 / 保温"}),
]


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, avatar TEXT NOT NULL, color TEXT NOT NULL, bio TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, name TEXT NOT NULL, brand TEXT NOT NULL, category TEXT NOT NULL, price REAL, description TEXT, art TEXT, color TEXT, specs TEXT NOT NULL, source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS friendships(a TEXT REFERENCES users(id), b TEXT REFERENCES users(id), PRIMARY KEY(a,b), CHECK(a<b));
            CREATE TABLE IF NOT EXISTS friend_requests(id INTEGER PRIMARY KEY, sender TEXT REFERENCES users(id), recipient TEXT REFERENCES users(id), status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS pending_friend ON friend_requests(min(sender,recipient),max(sender,recipient)) WHERE status='pending';
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, owner TEXT REFERENCES users(id), direct_key TEXT UNIQUE, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members(conversation_id TEXT REFERENCES conversations(id), user_id TEXT REFERENCES users(id), last_read INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(conversation_id,user_id));
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id), user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL, body TEXT NOT NULL, product_id TEXT REFERENCES products(id), artifact TEXT, client_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,client_id));
            CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id,id);
            CREATE TABLE IF NOT EXISTS ai_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id), context TEXT NOT NULL, role TEXT NOT NULL, body TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ai_context ON ai_messages(user_id,context,id);
            """)
            if not db.execute("SELECT 1 FROM meta WHERE key='seed_v1'").fetchone():
                self.seed(db)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self, db):
        users = [("u1", "林一", "林", "#bdd7cd", "发现生活里的好物"), ("u2", "周可", "可", "#e8c8b2", "数码爱好者 · 通勤党"), ("u3", "陈予", "予", "#cbc7e7", "实用主义，理性种草"), ("u4", "许知夏", "夏", "#e3d8a7", "一起分享日常灵感"), ("u5", "宋远", "远", "#c5d8e7", "户外与咖啡爱好者")]
        db.executemany("INSERT INTO users VALUES(?,?,?,?,?)", users)
        for p in PRODUCTS:
            db.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?)", (*p[:8], pack(p[8]), "演示商品目录 · 价格与参数为模拟快照"))
        db.executemany("INSERT INTO friendships VALUES(?,?)", [("u1", "u2"), ("u1", "u3"), ("u2", "u3")])
        stamp = now()
        db.execute("INSERT INTO conversations VALUES('g1','group','周末好物研究所','u1',NULL,?)", (stamp,))
        db.execute("INSERT INTO conversations VALUES('d1','direct','','u1','u1:u2',?)", (stamp,))
        db.executemany("INSERT INTO members(conversation_id,user_id) VALUES(?,?)", [("g1", "u1"), ("g1", "u2"), ("g1", "u3"), ("d1", "u1"), ("d1", "u2")])
        msgs = [("g1", "u1", "text", "想换一副通勤耳机，预算 600 元以内，大家有什么建议？", None), ("g1", "u2", "product", "看看这款，小米的价格比较合适。", "p4"), ("g1", "u3", "product", "我比较在意降噪，这款也可以比较一下。", "p5"), ("g1", "u2", "text", "我每天坐地铁，降噪和续航都很重要。", None), ("g1", "u1", "text", "还没确定，先看看这两款的区别？", None), ("g1", "u3", "text", "我来整理一下这两款的参数，今晚发到群里。", None), ("d1", "u2", "text", "欢迎来到拾物！看到喜欢的商品可以分享给我，一起研究。", None)]
        for i, m in enumerate(msgs):
            db.execute("INSERT INTO messages(conversation_id,user_id,kind,body,product_id,client_id,created_at) VALUES(?,?,?,?,?,?,?)", (*m, f"seed-{i}", stamp))
        db.execute("INSERT INTO meta VALUES('seed_v1','1')")


def product(row):
    if not row:
        return None
    result = dict(row)
    result["specs"] = json.loads(result["specs"])
    return result


def message(row):
    result = dict(row)
    if result.get("artifact"):
        result["artifact"] = json.loads(result["artifact"])
    return result
