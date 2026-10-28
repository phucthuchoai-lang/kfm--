import json
import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

try:
    from .store import now, pack, product, message
except ImportError:
    from store import now, pack, product, message


def fail(status, detail):
    raise HTTPException(status, detail)


def member(db, cid, uid):
    row = db.execute("SELECT c.* FROM conversations c JOIN members m ON m.conversation_id=c.id WHERE c.id=? AND m.user_id=?", (cid, uid)).fetchone()
    if not row:
        fail(403, "你不是该会话的成员，无法访问")
    return dict(row)


def get_messages(db, cid, where="", args=(), limit=40):
    rows = db.execute(f"SELECT m.*,u.name,u.avatar,u.color FROM messages m JOIN users u ON u.id=m.user_id WHERE m.conversation_id=? {where} ORDER BY m.id DESC LIMIT ?", (cid, *args, limit)).fetchall()
    return [message(r) for r in reversed(rows)]


def participants(db, cid):
    return [r[0] for r in db.execute("SELECT user_id FROM members WHERE conversation_id=?", (cid,))]


class Hub:
    def __init__(self):
        self.sockets = {}

    async def send(self, users, event):
        for uid in set(users):
            for socket in list(self.sockets.get(uid, set())):
                try:
                    await socket.send_json(event)
                except Exception:
                    self.sockets.get(uid, set()).discard(socket)


class Login(BaseModel):
    user_id: str = Field(min_length=1, max_length=30)


class FriendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=30)


class Group(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    member_ids: list[str] = Field(min_length=1, max_length=19)


class Members(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=19)


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class Outgoing(BaseModel):
    kind: Literal["text", "product", "ai"] = "text"
    body: str = Field(default="", max_length=4000)
    product_id: str | None = None
    artifact_id: int | None = None
    client_id: str = Field(min_length=8, max_length=100)


def install_platform(app, store):
    router = APIRouter(prefix="/api")
    hub = Hub()

    def auth(authorization: str | None = Header(default=None)):
        token = (authorization or "").removeprefix("Bearer ")
        with store.db() as db:
            user = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=?", (token,)).fetchone()
        if not user:
            fail(401, "请先选择演示账号")
        return dict(user)

    @router.get("/demo-users")
    def users():
        with store.db() as db:
            return {"users": [dict(r) for r in db.execute("SELECT * FROM users")], "demo": True}

    @router.post("/session")
    def login(data: Login):
        with store.db() as db:
            u = db.execute("SELECT * FROM users WHERE id=?", (data.user_id,)).fetchone()
            if not u:
                fail(404, "演示账号不存在")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (token, data.user_id, now()))
        return {"token": token, "user": dict(u), "demo": True}

    @router.get("/bootstrap")
    def bootstrap(user=Depends(auth)):
        uid = user["id"]
        with store.db() as db:
            friends = [dict(r) for r in db.execute("SELECT u.* FROM friendships f JOIN users u ON u.id=CASE WHEN f.a=? THEN f.b ELSE f.a END WHERE f.a=? OR f.b=?", (uid, uid, uid))]
            requests = [dict(r) for r in db.execute("SELECT f.*,u.name,u.avatar,u.color FROM friend_requests f JOIN users u ON u.id=f.sender WHERE f.recipient=? AND f.status='pending'", (uid,))]
            outgoing = [dict(r) for r in db.execute("SELECT * FROM friend_requests WHERE sender=? AND status='pending'", (uid,))]
            conversations = []
            for r in db.execute("SELECT c.*,m.last_read FROM conversations c JOIN members m ON m.conversation_id=c.id WHERE m.user_id=?", (uid,)):
                c = dict(r)
                c["members"] = [dict(x) for x in db.execute("SELECT u.* FROM users u JOIN members m ON m.user_id=u.id WHERE m.conversation_id=?", (c["id"],))]
                if c["kind"] == "direct":
                    peer = next((x for x in c["members"] if x["id"] != uid), user)
                    c.update(name=peer["name"], avatar=peer["avatar"], color=peer["color"])
                else:
                    c.update(avatar="群", color="#d6e7dc")
                last = get_messages(db, c["id"], limit=1)
                c["last_message"] = last[-1] if last else None
                c["unread"] = db.execute("SELECT count(*) FROM messages WHERE conversation_id=? AND id>? AND user_id<>?", (c["id"], c["last_read"], uid)).fetchone()[0]
                conversations.append(c)
        conversations.sort(key=lambda c: c["last_message"]["id"] if c["last_message"] else 0, reverse=True)
        return {"user": user, "friends": friends, "requests": requests, "outgoing": outgoing, "conversations": conversations}

    @router.get("/users")
    def search_users(q: str = Query(default="", max_length=50), user=Depends(auth)):
        with store.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM users WHERE id<>? AND (instr(name,?)>0 OR instr(id,?)>0) LIMIT 30", (user["id"], q, q))]

    @router.post("/friends/requests")
    async def request_friend(data: FriendRequest, user=Depends(auth)):
        uid, other = user["id"], data.user_id
        if uid == other:
            fail(400, "不能添加自己")
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM users WHERE id=?", (other,)).fetchone():
                fail(404, "账号不存在")
            a, b = sorted((uid, other))
            if db.execute("SELECT 1 FROM friendships WHERE a=? AND b=?", (a, b)).fetchone():
                fail(409, "你们已经是好友")
            if db.execute("SELECT 1 FROM friend_requests WHERE min(sender,recipient)=? AND max(sender,recipient)=? AND status='pending'", (a, b)).fetchone():
                fail(409, "已有待处理申请，请等待或处理对方申请")
            rid = db.execute("INSERT INTO friend_requests(sender,recipient,status,created_at) VALUES(?,?,'pending',?)", (uid, other, now())).lastrowid
        await hub.send([other, uid], {"type": "refresh"})
        return {"id": rid}

    @router.post("/friends/requests/{rid}/{action}")
    async def resolve_friend(rid: int, action: Literal["accept", "reject"], user=Depends(auth)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT * FROM friend_requests WHERE id=? AND recipient=? AND status='pending'", (rid, user["id"])).fetchone()
            if not r:
                fail(404, "申请不存在或已处理")
            db.execute("UPDATE friend_requests SET status=? WHERE id=?", (action, rid))
            if action == "accept":
                db.execute("INSERT OR IGNORE INTO friendships VALUES(?,?)", sorted((r["sender"], user["id"])))
            sender = r["sender"]
        await hub.send([sender, user["id"]], {"type": "refresh"})
        return {"ok": True}

    @router.post("/conversations/direct")
    async def direct(data: FriendRequest, user=Depends(auth)):
        uid, other = user["id"], data.user_id
        a, b = sorted((uid, other))
        key = f"{a}:{b}"
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM friendships WHERE a=? AND b=?", (a, b)).fetchone():
                fail(403, "请先添加为好友")
            row = db.execute("SELECT id FROM conversations WHERE direct_key=?", (key,)).fetchone()
            cid = row[0] if row else uuid.uuid4().hex
            if not row:
                db.execute("INSERT INTO conversations VALUES(?,'direct','',?,?,?)", (cid, uid, key, now()))
                db.executemany("INSERT INTO members(conversation_id,user_id) VALUES(?,?)", [(cid, uid), (cid, other)])
        await hub.send([uid, other], {"type": "refresh"})
        return {"id": cid}

    @router.post("/groups")
    async def group(data: Group, user=Depends(auth)):
        name = data.name.strip()
        if not name:
            fail(400, "请填写群名")
        uid = user["id"]
        mids = set(data.member_ids) - {uid}
        if not mids:
            fail(400, "请选择至少一位好友")
        cid = uuid.uuid4().hex
        with store.db() as db:
            for mid in mids:
                if not db.execute("SELECT 1 FROM friendships WHERE a=? AND b=?", sorted((uid, mid))).fetchone():
                    fail(403, "只能邀请自己的好友")
            db.execute("INSERT INTO conversations VALUES(?,'group',?,?,NULL,?)", (cid, name, uid, now()))
            db.executemany("INSERT INTO members(conversation_id,user_id) VALUES(?,?)", [(cid, mid) for mid in mids | {uid}])
        await hub.send(mids | {uid}, {"type": "refresh"})
        return {"id": cid}

    @router.patch("/groups/{cid}")
    async def rename(cid: str, data: Rename, user=Depends(auth)):
        with store.db() as db:
            c = member(db, cid, user["id"])
            if c["kind"] != "group" or c["owner"] != user["id"]:
                fail(403, "只有群主可以修改群名")
            if not data.name.strip():
                fail(400, "群名不能为空")
            db.execute("UPDATE conversations SET name=? WHERE id=?", (data.name.strip(), cid))
            mids = participants(db, cid)
        await hub.send(mids, {"type": "refresh"})
        return {"ok": True}

    @router.post("/groups/{cid}/members")
    async def invite(cid: str, data: Members, user=Depends(auth)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            c = member(db, cid, user["id"])
            if c["kind"] != "group" or c["owner"] != user["id"]:
                fail(403, "只有群主可以邀请成员")
            mids = set(participants(db, cid))
            added = set(data.user_ids) - mids
            if len(mids | added) > 20:
                fail(400, "演示群组最多 20 人")
            for mid in added:
                if not db.execute("SELECT 1 FROM friendships WHERE a=? AND b=?", sorted((user["id"], mid))).fetchone():
                    fail(403, "只能邀请自己的好友")
            db.executemany("INSERT INTO members(conversation_id,user_id) VALUES(?,?)", [(cid, mid) for mid in added])
        await hub.send(mids | added, {"type": "refresh"})
        return {"ok": True}

    @router.delete("/groups/{cid}/members/{uid}")
    async def leave(cid: str, uid: str, user=Depends(auth)):
        with store.db() as db:
            c = member(db, cid, user["id"])
            if c["kind"] != "group":
                fail(400, "单聊不能执行此操作")
            if uid != user["id"] and c["owner"] != user["id"]:
                fail(403, "只有群主可以移除其他成员")
            mids = participants(db, cid)
            if uid not in mids:
                fail(404, "成员不存在")
            if uid == c["owner"] and len(mids) > 1:
                fail(409, "群主请先移除其他成员，再退出群聊")
            db.execute("DELETE FROM members WHERE conversation_id=? AND user_id=?", (cid, uid))
        await hub.send(mids, {"type": "membership", "conversation_id": cid, "removed_user_id": uid})
        return {"ok": True}

    @router.get("/conversations/{cid}/messages")
    def messages(cid: str, before: int | None = None, around: int | None = None, limit: int = Query(default=40, ge=1, le=100), user=Depends(auth)):
        with store.db() as db:
            member(db, cid, user["id"])
            if around:
                if not db.execute("SELECT 1 FROM messages WHERE id=? AND conversation_id=?", (around, cid)).fetchone():
                    fail(404, "原消息不存在")
                result = get_messages(db, cid, "AND m.id<=?", (around,), max(1,limit//2))
                following = db.execute('SELECT m.*,u.name,u.avatar,u.color FROM messages m JOIN users u ON u.id=m.user_id WHERE m.conversation_id=? AND m.id>? ORDER BY m.id LIMIT ?', (cid,around,limit-len(result))).fetchall()
                result += [message(r) for r in following]
            else:
                result = get_messages(db, cid, "AND m.id<?" if before else "", (before,) if before else (), limit)
            oldest = result[0]["id"] if result else 0
            more = bool(oldest and db.execute("SELECT 1 FROM messages WHERE conversation_id=? AND id<?", (cid, oldest)).fetchone())
            newer = bool(result and db.execute('SELECT 1 FROM messages WHERE conversation_id=? AND id>?',(cid,result[-1]['id'])).fetchone())
        return {"messages": result, "has_more": more, "has_newer": newer}

    @router.post("/conversations/{cid}/read")
    def read(cid: str, user=Depends(auth)):
        with store.db() as db:
            member(db, cid, user["id"])
            db.execute("UPDATE members SET last_read=coalesce((SELECT max(id) FROM messages WHERE conversation_id=?),0) WHERE conversation_id=? AND user_id=?", (cid, cid, user["id"]))
        return {"ok": True}

    @router.post("/conversations/{cid}/messages")
    async def send(cid: str, data: Outgoing, user=Depends(auth)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            member(db, cid, user["id"])
            existing = db.execute("SELECT * FROM messages WHERE user_id=? AND client_id=?", (user["id"], data.client_id)).fetchone()
            if existing:
                if existing["conversation_id"] != cid:
                    fail(409, "消息标识已用于其他会话")
                if existing['kind'] != data.kind or (data.kind=='text' and existing['body'] != data.body.strip()) or (data.kind=='product' and existing['product_id'] != data.product_id):
                    fail(409, '消息标识与已保存内容不一致')
                return {"id": existing["id"], "duplicate": True}
            artifact = None
            body = data.body.strip()
            if data.kind == "text" and not body:
                fail(400, "消息不能为空")
            if data.kind == "product" and not db.execute("SELECT 1 FROM products WHERE id=?", (data.product_id,)).fetchone():
                fail(404, "商品不存在")
            if data.kind == "ai":
                row = db.execute("SELECT * FROM ai_messages WHERE id=? AND user_id=? AND role='assistant'", (data.artifact_id, user["id"])).fetchone()
                if not row:
                    fail(404, "AI 结果不存在")
                # A summary can only be shared back to its originating conversation.
                if row["context"].startswith("chat:") and row["context"] != f"chat:{cid}":
                    fail(403, "聊天分析仅能发送回原会话")
                artifact = row["payload"]
                body = row["body"]
            mid = db.execute("INSERT INTO messages(conversation_id,user_id,kind,body,product_id,artifact,client_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (cid, user["id"], data.kind, body, data.product_id if data.kind == "product" else None, artifact, data.client_id, now())).lastrowid
            mids = participants(db, cid)
        await hub.send(mids, {"type": "message", "conversation_id": cid, "message_id": mid})
        return {"id": mid, "duplicate": False}

    @router.get("/products")
    def products(q: str = Query(default="", max_length=100), category: str = "", brand: str = "", user=Depends(auth)):
        with store.db() as db:
            rows = [product(r) for r in db.execute("SELECT * FROM products ORDER BY (id LIKE 'mysql-%'), length(id), id")]
        return [p for p in rows if (not q or q.lower() in (p["name"] + p["brand"] + p["description"] + pack(p["specs"])).lower()) and (not category or p["category"] == category) and (not brand or p["brand"] == brand)]

    @router.get("/products/{pid}")
    def detail(pid: str, user=Depends(auth)):
        with store.db() as db:
            p = product(db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())
        if not p:
            fail(404, "商品不存在")
        return p

    @router.get('/products/{pid}/graph')
    def graph_evidence(pid: str, user=Depends(auth)):
        with store.db() as db:
            if not db.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone():
                fail(404,'商品不存在')
        if not pid.startswith('mysql-') or not pid[6:].isdigit():
            return {'status':'not_applicable','records':[], 'message':'该商品为独立演示数据，未关联原业务图谱。'}
        try:
            try:
                from .graph_tools import related_sku
            except ImportError:
                from graph_tools import related_sku
            records = related_sku(int(pid[6:]))
        except ValueError as e:
            fail(503,str(e))
        except Exception:
            fail(503,'图谱暂不可用，请检查只读账号、连接和索引；商品快照仍可使用。')
        return {'status':'ok' if records else 'no_match','records':records,'message':'固定参数化只读查询 · SKU 邻接关系'}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != ws.headers.get("host"):
            await ws.close(code=1008)
            return
        await ws.accept()
        uid = None
        try:
            import asyncio
            first = await asyncio.wait_for(ws.receive_json(), timeout=10)
            with store.db() as db:
                row = db.execute("SELECT user_id FROM sessions WHERE token=?", (first.get("token", ""),)).fetchone()
            if not row:
                await ws.close(code=1008)
                return
            uid = row[0]
            hub.sockets.setdefault(uid, set()).add(ws)
            await ws.send_json({"type": "connected", "user_id": uid})
            while True:
                await ws.receive_text()
                await ws.send_json({"type": "pong"})
        except (WebSocketDisconnect, ValueError):
            pass
        except Exception:
            await ws.close(code=1008)
        finally:
            if uid:
                hub.sockets.get(uid, set()).discard(ws)

    app.include_router(router)
    return auth
