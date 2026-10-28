"""Import a read-only MySQL catalog snapshot; never modifies MySQL or Neo4j."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.configuration.config import MYSQL_CONFIG
from src.web.store import Store, now, pack


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(ROOT / "data/runtime/platform.db"), help="Destination SQLite path")
    args = parser.parse_args()
    conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT s.id,s.sku_name,s.sku_desc,s.price,s.weight,s.is_sale,
                t.tm_name,c.name AS category FROM sku_info s
                LEFT JOIN base_trademark t ON t.id=s.tm_id
                LEFT JOIN base_category3 c ON c.id=s.category3_id ORDER BY s.id""")
            rows = cursor.fetchall()
    finally:
        conn.close()
    store = Store(args.database)
    with store.db() as db:
        for r in rows:
            name, cat = r["sku_name"], r["category"] or "其他"
            visual = "phone" if "手机" in cat else "buds" if "耳机" in cat else "watch" if "表" in cat else "bag" if "包" in cat else "coffee" if "咖啡" in name else "lamp" if "灯" in name else "box"
            specs = {"业务 SKU": str(r["id"]), "原始类别": cat, "重量（原始值）": str(r["weight"]) if r["weight"] is not None else None, "上架标记（快照）": str(r["is_sale"]) if r["is_sale"] is not None else None}
            db.execute("""INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,brand=excluded.brand,category=excluded.category,price=excluded.price,
                description=excluded.description,specs=excluded.specs,source=excluded.source,art=excluded.art""",
                (f"mysql-{r['id']}",name,r["tm_name"] or "未标注品牌",cat,float(r["price"]) if r["price"] is not None else None,r["sku_desc"] or "MySQL 业务商品快照",visual,"#d8dfcd",pack(specs),f"MySQL gmall.sku_info · SKU {r['id']} · 导入 {now()}"))
    print(f"Imported {len(rows)} SKU snapshots; source databases unchanged.")


if __name__ == "__main__":
    main()
