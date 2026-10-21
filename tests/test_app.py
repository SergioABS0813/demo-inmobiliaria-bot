import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from fastapi import HTTPException
from postgrest.exceptions import APIError
from app.main import app
from app.db import get_db
from app.schemas import VisitIn
from app.services import validate_timezone, request_fingerprint, normalize_property, LIMA


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.fields = db, table, {}, ''
    def select(self, fields): self.fields=fields;return self
    def eq(self, key, value): self.filters[key]=value;return self
    def limit(self, *args): return self
    def execute(self):
        self.db.queries.append((self.table,self.fields,self.filters.copy()))
        if self.table=='oportunidades':
            rows=[r.copy() for r in self.db.opportunities if r['token_uuid']==self.filters['token_uuid']]
        elif self.table=='visitas':
            rows=self.db.visits
            for key,value in self.filters.items():
                rows=[r for r in rows if r.get('lead_id' if key=='oportunidades.lead_id' else key)==value]
            rows=[r.copy() for r in rows]
        else: raise AssertionError('Consulta no esperada: '+self.table)
        return SimpleNamespace(data=rows)


class FakeDB:
    def __init__(self):
        self.token=str(uuid4());self.queries=[];self.calls=[];self.visits=[];self.rpc_error=None
        self.opportunities=[{'id':10,'token_uuid':self.token,'lead_id':42,'estado_id':9,
            'resultado':None,'fecha_cierre':None,'leads':{'id':42,'nombre':'Ana Pérez'},'estado_oportunidad':{'nombre':'nuevo'}}]
    def table(self,name): return Query(self,name)
    def rpc(self,name,args):
        self.calls.append((name,args))
        def execute():
            if self.rpc_error:raise self.rpc_error
            return SimpleNamespace(data=[] if name=='ru_mis_visitas_oportunidades' else {'id':8,'replayed':False})
        return SimpleNamespace(execute=execute)
    def add_visit(self,id=8,lead_id=42,opportunity_id=10,**extra):
        # lead_id is test fixture metadata, never an actual visitas column.
        row={'id':id,'lead_id':lead_id,'oportunidad_id':opportunity_id,
             'fecha_cliente':datetime.now(LIMA).isoformat(),'estado_id':4,
             'estados_visita':{'nombre':'Pendiente de coordinación'},'propiedades':{'id':1,'titulo':'Propiedad'},
             'oportunidades':{'lead_id':lead_id},**extra}
        self.visits.append(row);return row


class Rules(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB();app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app,raise_server_exceptions=False)
        self.headers={'X-Opportunity-Token':self.db.token}
    def tearDown(self):app.dependency_overrides.clear()
    def payload(self):
        return {'propiedad_id':1,'nombre':'Ana Pérez','fecha_cliente':(datetime.now(LIMA)+timedelta(days=2)).isoformat(),
                'consentimiento':True,'request_id':str(uuid4())}
    def test_missing_token_rejected(self):
        self.assertEqual(self.client.get('/api/lead/contexto').status_code,401)
    def test_invalid_token_never_reaches_rpc(self):
        response=self.client.post('/api/visitas',headers={'X-Opportunity-Token':str(uuid4())},json=self.payload())
        self.assertEqual(response.status_code,404);self.assertEqual(self.db.calls,[])
    def test_malformed_token(self):
        response=self.client.get('/api/lead/contexto',headers={'X-Opportunity-Token':'incorrecto'})
        self.assertEqual(response.status_code,404);self.assertIsInstance(response.json()['detail'],str)
    def test_legacy_header_is_opportunity_token(self):
        self.assertEqual(self.client.get('/api/lead/contexto',headers={'X-Lead-Token':self.db.token}).status_code,200)
    def test_conflicting_headers_rejected(self):
        response=self.client.get('/api/lead/contexto',headers={**self.headers,'X-Lead-Token':str(uuid4())})
        self.assertEqual(response.status_code,400)
    def test_context_privacy_and_token_resolution(self):
        self.db.opportunities[0]['leads']['telefono']='51999999999'
        response=self.client.get('/api/lead/contexto',headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertEqual(self.db.queries[0][0],'oportunidades')
        self.assertEqual(response.json()['telefono'],'51999999999')
        for field in ('id','lead_id','user_id','token_uuid','consentimiento'):self.assertNotIn(field,response.json())
    def test_closed_outcome_rejected(self):
        self.db.opportunities[0]['resultado']='ganada'
        self.assertEqual(self.client.get('/api/propiedades',headers=self.headers).status_code,403)
    def test_closed_date_rejected(self):
        self.db.opportunities[0]['fecha_cierre']=datetime.now(LIMA).isoformat()
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=self.payload()).status_code,403)
        self.assertEqual(self.db.calls,[])
    def test_requested_opportunity_remains_open(self):
        self.db.opportunities[0]['estado_oportunidad']['nombre']='visita_solicitada'
        self.assertEqual(self.client.get('/api/lead/contexto',headers=self.headers).status_code,200)
    def test_duplicate_tokens_fail_closed(self):
        self.db.opportunities.append(self.db.opportunities[0].copy())
        self.assertEqual(self.client.get('/api/lead/contexto',headers=self.headers).status_code,503)
    def test_missing_lead_fails_closed(self):
        self.db.opportunities[0]['leads']=None
        self.assertEqual(self.client.get('/api/lead/contexto',headers=self.headers).status_code,503)
    def test_foreign_ids_cannot_be_injected(self):
        for field in ('lead_id','oportunidad_id'):
            payload=self.payload();payload[field]=99
            self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
    def test_consent_is_request_validation(self):
        payload=self.payload();payload['consentimiento']=False
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
        self.assertEqual(self.db.calls,[])
    def test_timezone_is_explicit(self):
        payload=self.payload();payload['fecha_cliente']='2030-02-01T12:00:00'
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,422)
    def test_non_lima_offset_rejected(self):
        with self.assertRaises(HTTPException):validate_timezone(datetime.fromisoformat('2030-01-01T12:00:00+00:00'))
    def test_atomic_rpc_contract(self):
        response=self.client.post('/api/visitas',headers=self.headers,json=self.payload())
        self.assertEqual(response.status_code,201)
        name,args=self.db.calls[0];self.assertEqual(name,'ru_solicitar_visita_oportunidad')
        self.assertEqual(args['p_estado_oportunidad'],'visita_solicitada')
        for field in ('p_lead_id','p_oportunidad_id','fecha_acordada','fecha_agente'):self.assertNotIn(field,args)
        self.assertEqual(len(args['p_request_hash']),64)
    def test_existing_visit_returns_conflict_and_link(self):
        self.db.add_visit()
        response=self.client.post('/api/visitas',headers=self.headers,json=self.payload())
        self.assertEqual(response.status_code,409);self.assertEqual(response.json()['detail']['visita_id'],8)
        self.assertEqual(self.db.calls,[])
    def test_context_identifies_existing_visit(self):
        self.db.add_visit();data=self.client.get('/api/lead/contexto',headers=self.headers).json()
        self.assertFalse(data['puede_solicitar']);self.assertEqual(data['visita_id'],8)
    def test_identical_retry_replays(self):
        payload=self.payload();fingerprint=request_fingerprint(VisitIn(**payload))
        self.db.add_visit(request_id=payload['request_id'],request_hash=fingerprint)
        response=self.client.post('/api/visitas',headers=self.headers,json=payload)
        self.assertEqual(response.status_code,201);self.assertTrue(response.json()['replayed']);self.assertEqual(self.db.calls,[])
    def test_modified_retry_rejected(self):
        payload=self.payload();self.db.add_visit(request_id=payload['request_id'],request_hash='different')
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=payload).status_code,409)
    def test_concurrent_conflict_response(self):
        self.db.rpc_error=APIError({'message':'RU_VISIT_EXISTS','details':'27','code':'P0001','hint':None})
        response=self.client.post('/api/visitas',headers=self.headers,json=self.payload())
        self.assertEqual(response.status_code,409);self.assertEqual(response.json()['detail']['visita_id'],27)
    def test_closed_database_race(self):
        self.db.rpc_error=APIError({'message':'RU_CLOSED','details':None,'code':'P0001','hint':None})
        self.assertEqual(self.client.post('/api/visitas',headers=self.headers,json=self.payload()).status_code,403)
    def test_stable_fingerprint(self):
        payload=self.payload();one=VisitIn(**payload);payload['request_id']=str(uuid4())
        self.assertEqual(request_fingerprint(one),request_fingerprint(VisitIn(**payload)))
    def test_other_lead_visit_inaccessible(self):
        self.db.add_visit(id=55,lead_id=99,opportunity_id=20)
        self.assertEqual(self.client.get('/api/visitas/55',headers=self.headers).status_code,404)
    def test_same_lead_history_is_scoped_through_opportunities(self):
        self.db.add_visit(id=55,opportunity_id=20)
        response=self.client.get('/api/visitas/55',headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertFalse(response.json()['es_oportunidad_actual'])
        self.assertNotIn('lead_id',response.json());self.assertNotIn('oportunidades',response.json())
        self.assertEqual(self.db.queries[-1][2],{'oportunidades.lead_id':42,'id':55})
    def test_current_visit(self):
        self.db.add_visit();response=self.client.get('/api/visitas/actual',headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['es_oportunidad_actual'])
    def test_history_rpc_uses_token_not_lead_id(self):
        self.assertEqual(self.client.get('/api/visitas/mias',headers=self.headers).status_code,200)
        name,args=self.db.calls[0];self.assertEqual(name,'ru_mis_visitas_oportunidades')
        self.assertEqual(args['p_token'],self.db.token);self.assertNotIn('p_lead_id',args)
    def test_price_filter_validation(self):
        for url in ('/api/propiedades?precio_min=100','/api/propiedades?precio_min=200&precio_max=100&moneda=PEN'):
            self.assertEqual(self.client.get(url,headers=self.headers).status_code,422)
    def test_images_order(self):
        row={'distritos':{'nombre':'Lima'},'propiedad_imagenes':[{'id':3,'orden':None},{'id':2,'orden':2},{'id':1,'orden':1}]}
        self.assertEqual([x['id'] for x in normalize_property(row)['imagenes']],[1,2,3])
    def test_html_access_checked_server_side(self):
        for token in ('incorrecto',str(uuid4())):
            response=self.client.get('/inmuebles/'+token)
            self.assertEqual(response.status_code,404);self.assertIn('Este enlace no está disponible',response.text)
        self.db.opportunities[0]['resultado']='perdida'
        self.assertEqual(self.client.get('/inmuebles/'+self.db.token).status_code,403)
    def test_valid_pages_keep_security_headers(self):
        for suffix in ('','/propiedad/1','/propiedad/1/solicitar','/mis-visitas','/confirmacion/1'):
            response=self.client.get('/inmuebles/'+self.db.token+suffix)
            self.assertEqual(response.status_code,200,suffix)
            self.assertEqual(response.headers['referrer-policy'],'no-referrer')
            self.assertEqual(response.headers['cache-control'],'no-store')
    def test_health_not_database_check(self):
        self.assertFalse(self.client.get('/api/health').json()['database_checked'])
    def test_no_inner_html(self):
        for file in (Path(__file__).resolve().parents[1]/'static/js').glob('*.js'):
            self.assertNotIn('innerHTML',file.read_text(encoding='utf-8'),str(file))


if __name__=='__main__':unittest.main()
