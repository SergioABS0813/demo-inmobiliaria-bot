import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError
from app.main import app
from app.db import get_db
from app.schemas import VisitIn
from app.services import validate_timezone, request_fingerprint, normalize_property, LIMA


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, {}
    def select(self, *args): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def limit(self, *args): return self
    def execute(self):
        self.db.last_query = (self.table, self.filters)
        if self.table == 'leads':
            data = [{'id': 42, 'nombre':'Ana Pérez', 'consentimiento':False}] if self.filters.get('token_uuid') == self.db.token else []
        else:
            data = []
        return SimpleNamespace(data=data)


class FakeDB:
    def __init__(self): self.token = str(uuid4()); self.calls = []; self.last_query = None
    def table(self, name): return Query(self, name)
    def rpc(self, name, args):
        self.calls.append((name,args))
        return SimpleNamespace(execute=lambda:SimpleNamespace(data={'id':8,'nombre':'VIS-000008','replayed':False}))


class Rules(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB(); app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app, raise_server_exceptions=False)
        self.headers={'X-Lead-Token':self.db.token}
    def tearDown(self): app.dependency_overrides.clear()
    def payload(self):
        return {'propiedad_id':1,'nombre':'Ana Pérez','fecha_cliente':(datetime.now(LIMA)+timedelta(days=2)).isoformat(), 'consentimiento':True,'request_id':str(uuid4())}
    def test_missing_token_rejected(self):
        self.assertEqual(self.client.get('/api/lead/contexto').status_code,422)
    def test_invalid_token_never_reaches_rpc(self):
        response=self.client.post('/api/visitas',headers={'X-Lead-Token':str(uuid4())},json=self.payload())
        self.assertEqual(response.status_code,404); self.assertEqual(self.db.calls,[])
    def test_malformed_token_has_friendly_error(self):
        response=self.client.get('/api/lead/contexto',headers={'X-Lead-Token':'enlace-invalido'})
        self.assertEqual(response.status_code,404)
        self.assertIsInstance(response.json()['detail'],str)
    def test_context_minimizes_personal_data(self):
        response=self.client.get('/api/lead/contexto',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('user_id',response.json()); self.assertNotIn('id',response.json()); self.assertNotIn('token_uuid',response.json())
    def test_lead_cannot_be_injected(self):
        payload=self.payload();payload['lead_id']=99
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
    def test_consent_is_required(self):
        payload=self.payload();payload['consentimiento']=False
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
        self.assertEqual(self.db.calls,[])
    def test_timezone_is_explicit(self):
        payload=self.payload();payload['fecha_cliente']='2030-02-01T12:00:00'
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
    def test_non_lima_offset_rejected(self):
        with self.assertRaises(HTTPException): validate_timezone(datetime.fromisoformat('2030-01-01T12:00:00+00:00'))
        validate_timezone(datetime.now(LIMA))
    def test_atomic_rpc_contract(self):
        response=self.client.post('/api/visitas',headers=self.headers,json=self.payload())
        self.assertEqual(response.status_code,201)
        name,args=self.db.calls[0]; self.assertEqual(name,'ru_solicitar_visita')
        self.assertNotIn('lead_id',args);self.assertNotIn('fecha_acordada',args);self.assertNotIn('fecha_agente',args)
        self.assertEqual(len(args['p_request_hash']),64)
    def test_stable_fingerprint_across_retry_keys(self):
        payload=self.payload();one=VisitIn(**payload);payload['request_id']=str(uuid4());two=VisitIn(**payload)
        self.assertEqual(request_fingerprint(one),request_fingerprint(two))
        payload['nombre']='Otra persona'; self.assertNotEqual(request_fingerprint(one),request_fingerprint(VisitIn(**payload)))
    def test_visits_are_scoped_to_lead(self):
        self.assertEqual(self.client.get('/api/visitas/9',headers=self.headers).status_code,404)
        self.assertEqual(self.db.last_query,('visitas',{'lead_id':42,'id':9}))
    def test_filter_prices_require_currency(self):
        response=self.client.get('/api/propiedades?precio_min=100',headers=self.headers)
        self.assertEqual(response.status_code,422)
    def test_filter_range(self):
        response=self.client.get('/api/propiedades?precio_min=200&precio_max=100&moneda=PEN',headers=self.headers)
        self.assertEqual(response.status_code,422)
    def test_property_images_order(self):
        row={'distritos':{'nombre':'Lima'},'propiedad_imagenes':[{'id':3,'orden':None},{'id':2,'orden':2},{'id':1,'orden':1}]}
        self.assertEqual([x['id'] for x in normalize_property(row)['imagenes']],[1,2,3])
    def test_security_headers_and_pages(self):
        for path in ('/',f'/inmuebles/{self.db.token}',f'/inmuebles/{self.db.token}/propiedad/1',f'/inmuebles/{self.db.token}/propiedad/1/solicitar',f'/inmuebles/{self.db.token}/mis-visitas',f'/inmuebles/{self.db.token}/confirmacion/1'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,path)
            self.assertEqual(response.headers['referrer-policy'],'no-referrer')
            self.assertEqual(response.headers['cache-control'],'no-store')
    def test_health_does_not_claim_database_check(self):
        self.assertFalse(self.client.get('/api/health').json()['database_checked'])
    def test_no_inner_html_for_database_content(self):
        for file in (Path(__file__).resolve().parents[1]/'static/js').glob('*.js'):
            self.assertNotIn('innerHTML',file.read_text(encoding='utf-8'),str(file))


if __name__=='__main__': unittest.main()
