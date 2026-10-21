import unittest
from uuid import uuid4
from types import SimpleNamespace
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from app.main import app
from app.db import get_db
from test_app import FakeDB
import test_app


class PropertyOpportunity(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB()
        self.db.opportunities[0]['propiedad_id']=5
        self.new_token=str(uuid4())
        old_rpc=self.db.rpc
        def rpc(name,args):
            if name!='ru_resolver_oportunidad_propiedad':return old_rpc(name,args)
            self.db.calls.append((name,args))
            def execute():
                if self.db.rpc_error:raise self.db.rpc_error
                return SimpleNamespace(data={'token_uuid':self.new_token,'propiedad_id':None,'visita_id':None})
            return SimpleNamespace(execute=execute)
        self.db.rpc=rpc
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app,raise_server_exceptions=False)
        self.headers={'X-Opportunity-Token':self.db.token}
    def tearDown(self):app.dependency_overrides.clear()
    def test_context_includes_property_binding(self):
        self.assertEqual(self.client.get('/api/lead/contexto',headers=self.headers).json()['propiedad_id'],5)
    def test_resolve_uses_authorized_token_not_browser_lead(self):
        response=self.client.post('/api/oportunidades/resolver',headers=self.headers,json={'propiedad_id':8})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['token_uuid'],self.new_token)
        self.assertEqual(self.db.calls[0],('ru_resolver_oportunidad_propiedad',{'p_token':self.db.token,'p_propiedad_id':8}))
        self.assertEqual(self.db.opportunities[0]['propiedad_id'],5)
    def test_resolve_forbids_identity_override(self):
        response=self.client.post('/api/oportunidades/resolver',headers=self.headers,json={'propiedad_id':8,'lead_id':999})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.db.calls,[])
    def test_resolve_rejects_unauthorized_and_closed(self):
        for headers,code in [({},401),({'X-Opportunity-Token':str(uuid4())},404)]:
            self.assertEqual(self.client.post('/api/oportunidades/resolver',headers=headers,json={'propiedad_id':8}).status_code,code)
        self.db.opportunities[0]['resultado']='ganada'
        self.assertEqual(self.client.post('/api/oportunidades/resolver',headers=self.headers,json={'propiedad_id':8}).status_code,403)
        self.assertEqual(self.db.calls,[])
    def test_different_property_is_controlled_conflict(self):
        payload=test_app.Rules.payload(self)
        payload['propiedad_id']=8
        response=self.client.post('/api/visitas',headers=self.headers,json=payload)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['detail']['code'],'RU_PROPERTY_MISMATCH')
        self.assertEqual(self.db.calls,[])
    def test_same_property_still_uses_atomic_rpc(self):
        payload=test_app.Rules.payload(self);payload['propiedad_id']=5
        response=self.client.post('/api/visitas',headers=self.headers,json=payload)
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.db.calls[0][0],'ru_solicitar_visita_oportunidad')
    def test_database_concurrent_property_conflicts(self):
        payload=test_app.Rules.payload(self);payload['propiedad_id']=5
        for tag in ('RU_PROPERTY_MISMATCH','RU_PROPERTY_ALREADY_OPEN'):
            self.db.rpc_error=APIError({'code':'P0001','message':tag,'details':None,'hint':None})
            response=self.client.post('/api/visitas',headers=self.headers,json=payload)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['detail']['code'],tag)
    def test_existing_target_visit_and_replay_contract(self):
        payload=test_app.Rules.payload(self);payload['propiedad_id']=5
        from app.schemas import VisitIn
        from app.services import request_fingerprint
        self.db.add_visit(request_id=payload['request_id'],request_hash=request_fingerprint(VisitIn(**payload)))
        response=self.client.post('/api/visitas',headers=self.headers,json=payload)
        self.assertEqual(response.status_code,201)
        self.assertTrue(response.json()['replayed'])
        self.assertEqual(self.db.calls,[])
    def test_missing_resolver_migration_has_actionable_message(self):
        self.db.rpc_error=APIError({'code':'PGRST202','message':'Missing function','details':None,'hint':None})
        response=self.client.post('/api/oportunidades/resolver',headers=self.headers,json={'propiedad_id':8})
        self.assertEqual(response.status_code,503)
        self.assertIn('migracion 06',response.json()['detail'])
