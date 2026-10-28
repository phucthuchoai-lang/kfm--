"""Optional graph evidence through a fixed parameterized read query."""
import os


def related_sku(sku_id):
    from neo4j import GraphDatabase, Query, READ_ACCESS
    user, password = os.getenv('NEO4J_READ_USERNAME'), os.getenv('NEO4J_READ_PASSWORD')
    if not user or not password:
        raise ValueError('未配置独立的 Neo4j 只读账号。请设置 NEO4J_READ_USERNAME 和 NEO4J_READ_PASSWORD。')
    query = '''MATCH (sku:SKU {id:$sku_id})
        OPTIONAL MATCH (sku)-[r]-(neighbor)
        RETURN sku.id AS sku_id, sku.name AS sku_name,
            type(r) AS relation, labels(neighbor) AS labels,
            neighbor.id AS related_id, neighbor.name AS related_name LIMIT 30'''
    with GraphDatabase.driver(os.getenv('NEO4J_URI','neo4j://127.0.0.1:7687'),auth=(user,password),connection_timeout=5) as driver:
        with driver.session(default_access_mode=READ_ACCESS) as session:
            return [r.data() for r in session.run(Query(query,timeout=5),sku_id=sku_id)]
