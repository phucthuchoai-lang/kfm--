import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from src.web.app import create_app
from src.web.store import Store


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/"test.db"
        self.app = create_app(self.path)
        self.client = TestClient(self.app)
        self.headers = {u:{"Authorization":"Bearer "+self.client.post('/api/session',json={'user_id':u}).json()['token']} for u in ['u1','u2','u3','u4','u5']}
        self.env = patch.dict(os.environ, {'AI_MODE':'local'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.client.close()
        self.tmp.cleanup()

    def get(self,path,u='u1'):
        return self.client.get('/api'+path,headers=self.headers[u])

    def post(self,path,data=None,u='u1'):
        return self.client.post('/api'+path,json=data or {},headers=self.headers[u])

    def send(self,body='hello',cid='g1',u='u1',**extra):
        return self.post(f'/conversations/{cid}/messages',{'body':body,'client_id':uuid.uuid4().hex,**extra},u)

    def ask(self,**data):
        return self.post('/assistant/ask',data)

    def make_group(self):
        return self.post('/groups',{'name':'测试群','member_ids':['u2','u3']}).json()['id']

    def test_01_health(self):
        r=self.get('/health').json(); self.assertEqual(r['status'],'ok'); self.assertTrue(r['demo']); self.assertFalse(r['external_services_checked'])

    def test_02_auth_required(self):
        self.assertEqual(self.client.get('/api/bootstrap').status_code,401)

    def test_03_invalid_account(self):
        self.assertEqual(self.post('/session',{'user_id':'unknown'}).status_code,404)

    def test_04_catalog_and_filter(self):
        self.assertEqual(len(self.get('/products').json()),12)
        self.assertEqual(len(self.get('/products?category=耳机&brand=华为').json()),1)
        self.assertEqual(self.get('/products?q=absent').json(),[])

    def test_05_product_detail(self):
        self.assertIn('演示',self.get('/products/p1').json()['source'])
        self.assertEqual(self.get('/products/unknown').status_code,404)

    def test_06_self_friend(self):
        self.assertEqual(self.post('/friends/requests',{'user_id':'u1'}).status_code,400)

    def test_07_existing_friend(self):
        self.assertEqual(self.post('/friends/requests',{'user_id':'u2'}).status_code,409)

    def test_08_request_acceptance(self):
        r=self.post('/friends/requests',{'user_id':'u4'});self.assertEqual(r.status_code,200)
        rid=r.json()['id'];self.assertEqual(len(self.get('/bootstrap','u4').json()['requests']),1)
        self.assertEqual(self.post(f'/friends/requests/{rid}/accept',u='u4').status_code,200)
        self.assertIn('u4',[u['id'] for u in self.get('/bootstrap').json()['friends']])
        self.assertIn('u1',[u['id'] for u in self.get('/bootstrap','u4').json()['friends']])

    def test_09_reciprocal_duplicate(self):
        self.post('/friends/requests',{'user_id':'u4'})
        self.assertEqual(self.post('/friends/requests',{'user_id':'u1'},'u4').status_code,409)

    def test_10_request_permissions(self):
        rid=self.post('/friends/requests',{'user_id':'u4'}).json()['id']
        self.assertEqual(self.post(f'/friends/requests/{rid}/accept',u='u3').status_code,404)

    def test_11_reject_request(self):
        rid=self.post('/friends/requests',{'user_id':'u4'}).json()['id']
        self.post(f'/friends/requests/{rid}/reject',u='u4')
        self.assertNotIn('u4',[u['id'] for u in self.get('/bootstrap').json()['friends']])

    def test_12_direct_friend_required(self):
        self.assertEqual(self.post('/conversations/direct',{'user_id':'u4'}).status_code,403)

    def test_13_direct_idempotent(self):
        a=self.post('/conversations/direct',{'user_id':'u2'}).json()['id']
        b=self.post('/conversations/direct',{'user_id':'u1'},'u2').json()['id'];self.assertEqual(a,b)

    def test_14_group_creation(self):
        cid=self.make_group();self.assertEqual(self.get(f'/conversations/{cid}/messages','u2').status_code,200)

    def test_15_group_nonfriend(self):
        self.assertEqual(self.post('/groups',{'name':'group','member_ids':['u4']}).status_code,403)

    def test_16_empty_group_name(self):
        self.assertEqual(self.post('/groups',{'name':'  ','member_ids':['u2']}).status_code,400)

    def test_17_rename_permission(self):
        r=self.client.patch('/api/groups/g1',json={'name':'new'},headers=self.headers['u2']);self.assertEqual(r.status_code,403)
        r=self.client.patch('/api/groups/g1',json={'name':'new'},headers=self.headers['u1']);self.assertEqual(r.status_code,200)

    def test_18_invite_permission(self):
        self.assertEqual(self.post('/groups/g1/members',{'user_ids':['u4']},'u2').status_code,403)

    def test_19_invite_friend(self):
        rid=self.post('/friends/requests',{'user_id':'u4'}).json()['id'];self.post(f'/friends/requests/{rid}/accept',u='u4')
        self.assertEqual(self.post('/groups/g1/members',{'user_ids':['u4']}).status_code,200)
        self.assertEqual(self.get('/conversations/g1/messages','u4').status_code,200)

    def test_20_outsider_read_denied(self):
        self.assertEqual(self.get('/conversations/g1/messages','u4').status_code,403)

    def test_21_outsider_write_denied(self):
        self.assertEqual(self.send(u='u4').status_code,403)

    def test_22_member_cannot_remove_others(self):
        self.assertEqual(self.client.delete('/api/groups/g1/members/u3',headers=self.headers['u2']).status_code,403)

    def test_23_removed_member_loses_access(self):
        self.assertEqual(self.client.delete('/api/groups/g1/members/u2',headers=self.headers['u1']).status_code,200)
        self.assertEqual(self.get('/conversations/g1/messages','u2').status_code,403)
        self.assertEqual(self.post('/assistant/ask',{'action':'summary','conversation_id':'g1'},'u2').status_code,403)

    def test_24_leave_and_owner_guard(self):
        self.assertEqual(self.client.delete('/api/groups/g1/members/u1',headers=self.headers['u1']).status_code,409)
        self.assertEqual(self.client.delete('/api/groups/g1/members/u2',headers=self.headers['u2']).status_code,200)

    def test_25_empty_and_long_messages(self):
        self.assertEqual(self.send(body=' ').status_code,400)
        self.assertEqual(self.send(body='x'*4001).status_code,422)

    def test_26_missing_product(self):
        self.assertEqual(self.send(kind='product',product_id='absent').status_code,404)

    def test_27_product_share(self):
        self.send(body='看看这款',kind='product',product_id='p1')
        self.assertEqual(self.get('/conversations/g1/messages').json()['messages'][-1]['product_id'],'p1')

    def test_28_message_idempotency(self):
        key=uuid.uuid4().hex;a=self.send(client_id=key).json();b=self.send(client_id=key).json()
        self.assertEqual(a['id'],b['id']);self.assertTrue(b['duplicate'])

    def test_29_key_not_reused_cross_conversation(self):
        key=uuid.uuid4().hex;self.send(client_id=key)
        self.assertEqual(self.send(cid='d1',client_id=key).status_code,409)

    def test_30_message_pagination(self):
        r=self.get('/conversations/g1/messages?limit=2').json();self.assertTrue(r['has_more']);self.assertEqual(len(r['messages']),2)
        older=self.get('/conversations/g1/messages?before='+str(r['messages'][0]['id'])).json()['messages'];self.assertLess(older[-1]['id'],r['messages'][0]['id'])

    def test_31_reference_is_scoped(self):
        self.assertEqual(self.get('/conversations/g1/messages?around=7').status_code,404)
        around=self.get('/conversations/g1/messages?around=2').json()
        self.assertIn(2,[m['id'] for m in around['messages']]);self.assertFalse(around['has_newer'])

    def test_32_read_marker(self):
        self.post('/conversations/g1/read')
        c=next(c for c in self.get('/bootstrap').json()['conversations'] if c['id']=='g1');self.assertEqual(c['unread'],0)

    def test_33_restart_keeps_data(self):
        self.send('keep me');Store(self.path)
        self.assertEqual(self.get('/conversations/g1/messages').json()['messages'][-1]['body'],'keep me')

    def test_34_websocket_delivery(self):
        token=self.headers['u2']['Authorization'].split()[1]
        with self.client.websocket_connect('/ws') as ws:
            ws.send_json({'token':token});self.assertEqual(ws.receive_json()['type'],'connected')
            self.send('live')
            event=ws.receive_json();self.assertEqual(event['type'],'message');self.assertEqual(event['conversation_id'],'g1')
            ws.send_text('ping');self.assertEqual(ws.receive_json()['type'],'pong')

    def test_35_compare_sources(self):
        r=self.ask(action='compare',product_ids=['p4','p5']).json();self.assertEqual(r['mode'],'local');self.assertEqual(len(r['comparison']['products']),2)
        self.assertEqual(r['comparison']['rows'][0]['values'],['¥199','¥499']);self.assertEqual(len(r['sources']),2)

    def test_36_compare_selection_validation(self):
        self.assertEqual(self.ask(action='compare',product_ids=['p1']).status_code,400)
        self.assertEqual(self.ask(action='compare',product_ids=['p1','absent']).status_code,404)

    def test_37_summary_traceability(self):
        r=self.ask(action='summary',conversation_id='g1').json();allowed={m['id'] for m in r['source_messages']}
        for s in r['sections']:
            for item in s['items']:self.assertTrue(set(item['message_ids'])<=allowed)
        self.assertEqual(next(s['items'] for s in r['sections'] if s['title']=='明确结论'),[])
        self.assertIn('陈予',r['message']);self.assertEqual(len(r['products']),2)

    def test_38_summary_scope(self):
        r=self.ask(action='summary',conversation_id='g1',scope='recent',recent_count=2).json();self.assertEqual(len(r['source_messages']),2)
        self.assertEqual(self.ask(action='summary').status_code,400)

    def test_39_range_validation(self):
        self.assertEqual(self.ask(action='summary',conversation_id='g1',scope='range').status_code,400)
        self.assertEqual(self.ask(action='summary',conversation_id='g1',scope='range',start='2020-01-01T00:00:00+08:00',end='2020-01-02T00:00:00+08:00').status_code,400)

    def test_40_ai_history_isolation(self):
        self.ask(message='小米手机')
        self.assertEqual(len(self.get('/assistant/history').json()['messages']),2)
        self.assertEqual(self.get('/assistant/history','u2').json()['messages'],[])
        self.assertEqual(self.get('/assistant/history?conversation_id=g1').json()['messages'],[])

    def test_41_ai_no_match(self):
        r=self.ask(message='不存在的品牌XYZ').json();self.assertEqual(r['status'],'no_match');self.assertEqual(r['products'],[])

    def test_42_multiturn_filter(self):
        self.ask(message='推荐小米耳机')
        r=self.ask(message='换成华为，预算600元以内').json();self.assertEqual([p['id'] for p in r['products']],['p5'])

    def test_43_share_ai_requires_owner(self):
        r=self.ask(action='compare',product_ids=['p4','p5']).json()
        self.assertEqual(self.send(kind='ai',artifact_id=r['id'],u='u2').status_code,404)
        self.assertEqual(self.send(kind='ai',artifact_id=r['id']).status_code,200)

    def test_44_summary_cannot_leak_to_other_conversation(self):
        r=self.ask(action='summary',conversation_id='g1').json()
        self.assertEqual(self.send(cid='d1',kind='ai',artifact_id=r['id']).status_code,403)

    def test_45_cloud_failure_is_labelled(self):
        import httpx
        with patch('src.web.assistant_api.cloud_wording',new=AsyncMock(side_effect=httpx.ConnectError('test'))):
            r=self.ask(message='耳机').json();self.assertEqual(r['mode'],'local');self.assertIn('模型暂不可用',r['notice'])

    def test_46_missing_values_remain_missing(self):
        r=self.ask(action='compare',product_ids=['p1','p3']).json()
        row=next(r for r in r['comparison']['rows'] if r['label']=='电池');self.assertEqual(row['values'][1],'暂无数据')

    def test_47_other_chat_ai_history_forbidden(self):
        self.assertEqual(self.get('/assistant/history?conversation_id=g1','u5').status_code,403)

    def test_48_new_message_makes_summary_stale(self):
        r=self.ask(action='summary',conversation_id='g1').json();self.send('新的补充')
        h=self.get('/assistant/history?conversation_id=g1').json();self.assertGreater(h['latest_message_id'],r['last_message_id'])

    def test_49_model_summary_bad_citation_falls_back(self):
        with patch('src.web.assistant_api.cloud_summary',new=AsyncMock(side_effect=ValueError('invalid ref'))):
            r=self.ask(action='summary',conversation_id='g1').json();self.assertEqual(r['mode'],'local');self.assertIn('引用校验',r['notice'])

    def test_50_timestamp_range(self):
        r=self.ask(action='summary',conversation_id='g1',scope='range',start='2026-01-01T00:00:00+08:00',end='2100-01-01T00:00:00+08:00')
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['source_messages']),6)

    def test_51_summary_size_limit(self):
        with self.app.state.store.db() as db:
            db.executemany("INSERT INTO messages(conversation_id,user_id,kind,body,client_id,created_at) VALUES('g1','u1','text','test',?,'2026-10-27T00:00:00+00:00')",[(f'bulk-{i}',) for i in range(1001)])
        self.assertEqual(self.ask(action='summary',conversation_id='g1',scope='all').status_code,413)

    def test_52_demo_has_no_fake_graph(self):
        r=self.get('/products/p1/graph').json();self.assertEqual(r['status'],'not_applicable');self.assertEqual(r['records'],[])

    def test_53_graph_requires_read_account(self):
        with self.app.state.store.db() as db:
            db.execute("INSERT INTO products SELECT 'mysql-1',name,brand,category,price,description,art,color,specs,'MySQL snapshot' FROM products WHERE id='p1'")
        with patch.dict(os.environ,{'NEO4J_READ_USERNAME':'','NEO4J_READ_PASSWORD':''}):
            self.assertEqual(self.get('/products/mysql-1/graph').status_code,503)

    def test_54_changed_duplicate_content_rejected(self):
        key=uuid.uuid4().hex;self.send(body='first',client_id=key)
        self.assertEqual(self.send(body='second',client_id=key).status_code,409)

    def test_55_new_unrelated_question_clears_product_context(self):
        self.ask(message='小米耳机')
        self.assertEqual(self.ask(message='XYZ不存在的商品').json()['status'],'no_match')

    def test_56_query_validation(self):
        self.assertEqual(self.get('/conversations/g1/messages?limit=101').status_code,422)
        self.assertEqual(self.ask(action='compare',product_ids=['p1','p2','p3','p4','p5']).status_code,422)

    def test_57_output_cannot_execute_html(self):
        text='<img src=x onerror=alert(1)>'
        self.send(body=text)
        self.assertEqual(self.get('/conversations/g1/messages').json()['messages'][-1]['body'],text)
        self.assertIn("script-src 'self'",self.get('/health').headers['content-security-policy'])

    def test_58_reconnection_has_history(self):
        token=self.headers['u2']['Authorization'].split()[1]
        with self.client.websocket_connect('/ws') as ws:
            ws.send_json({'token':token});ws.receive_json()
        self.send(body='while disconnected')
        with self.client.websocket_connect('/ws') as ws:
            ws.send_json({'token':token});self.assertEqual(ws.receive_json()['type'],'connected')
        self.assertEqual(self.get('/conversations/g1/messages','u2').json()['messages'][-1]['body'],'while disconnected')


if __name__=='__main__':
    unittest.main()
