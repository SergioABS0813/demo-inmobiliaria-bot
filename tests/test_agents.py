import unittest
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.config import get_settings
from postgrest.exceptions import APIError


class Query:
    def __init__(self, db, table):
        self.db=db;self.table=table;self.filters={};self.span=None;self.head=False
    def select(self,*args,**kwargs):self.head=kwargs.get("head",False);return self
    def eq(self,k,v):self.filters[k]=v;return self
    def is_(self,k,v):self.filters[k]=None;return self
    def limit(self,*args):return self
    def order(self,*args,**kwargs):return self
    def range(self,start,end):self.span=(start,end);return self
    def execute(self):
        self.db.calls.append(self)
        if self.table=='agentes':
            rows=self.db.agents if self.filters['token_uuid']==self.db.token else []
        else:
            rows=[v for v in self.db.visits if v['propiedades']['tipo_inmueble']==self.filters['propiedades.tipo_inmueble'] and v['estados_visita']['nombre']==self.filters['estados_visita.nombre'] and ('oportunidades.resultado' not in self.filters or v['oportunidades']['resultado'] is None) and ('oportunidades.fecha_cierre' not in self.filters or v['oportunidades']['fecha_cierre'] is None)]
            count=len(rows)
            if self.span is not None:rows=rows[self.span[0]:self.span[1]+1]
        return SimpleNamespace(data=deepcopy(rows),count=len(rows) if self.head else None)


class Agents(unittest.TestCase):
    def setUp(self):
        self.db=SimpleNamespace(token=str(uuid4()),calls=[],agents=[{'id':1,'nombre':'Ana','especialidad':'Departamento'}],visits=[],rpc_calls=[],rpc_error=None)
        self.db.table=lambda table:Query(self.db,table)
        def rpc(name,params):
            self.db.rpc_calls.append((name,params))
            def execute():
                if self.db.rpc_error:raise self.db.rpc_error
                visit=next((v for v in self.db.visits if v['id']==params['p_visita_id']),None)
                tag=None
                if visit is None or visit['propiedades']['tipo_inmueble']!=self.db.agents[0]['especialidad']:tag='RU_AGENT_VISIT'
                elif visit['estados_visita']['nombre']=='contactada':tag='RU_AGENT_CONTACTED'
                elif visit['estados_visita']['nombre']!=params['p_estado_pendiente']:tag='RU_AGENT_PENDING'
                if tag:raise APIError({'code':'P0001','message':tag,'details':None,'hint':None})
                visit['estados_visita']['nombre']='contactada'
                return SimpleNamespace(data={'id':visit['id'],'estado':'contactada'})
            return SimpleNamespace(execute=execute)
        self.db.rpc=rpc
        for i,kind in enumerate(['Departamento','Casa']):
            self.db.visits.append({'id':i+1,'propiedades':{'tipo_inmueble':kind,'titulo':kind},'estados_visita':{'nombre':get_settings().initial_visit_state},'oportunidades':{'resultado':None,'fecha_cierre':None,'leads':{'nombre':'Cliente','telefono':'51999999999'}}})
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app)
        self.headers={'X-Agent-Token':self.db.token}
    def tearDown(self):app.dependency_overrides.clear()
    def test_access_requires_agent_token(self):
        for headers,code in [({},401),({'X-Agent-Token':'bad'},404),({'X-Agent-Token':str(uuid4())},404),({'X-Opportunity-Token':self.db.token},401)]:
            self.assertEqual(self.client.get('/api/agentes/visitas',headers=headers).status_code,code)
        self.assertFalse(any(q.table=='visitas' for q in self.db.calls))
    def test_specialty_filter_and_contact(self):
        response=self.client.get('/api/agentes/visitas',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()),1)
        self.assertEqual(response.json()[0]['cliente']['telefono'],'51999999999')
        self.assertNotIn('oportunidades',response.json()[0])
        self.assertEqual(self.db.calls[-1].filters['propiedades.tipo_inmueble'],'Departamento')
    def test_shared_specialty(self):
        first=self.client.get('/api/agentes/visitas',headers=self.headers).json()
        self.db.agents[0]['id']=2
        self.assertEqual(self.client.get('/api/agentes/visitas',headers=self.headers).json(),first)
    def test_closed_and_other_states_excluded(self):
        self.db.visits[0]['oportunidades']['resultado']='ganada'
        self.assertEqual(self.client.get('/api/agentes/visitas',headers=self.headers).json(),[])
        self.db.visits[0]['oportunidades']['resultado']=None
        self.db.visits[0]['estados_visita']['nombre']='cancelada'
        self.assertEqual(self.client.get('/api/agentes/visitas',headers=self.headers).json(),[])
    def test_missing_specialty_and_ambiguous_token(self):
        self.db.agents[0]['especialidad']=' '
        self.assertEqual(self.client.get('/api/agentes/contexto',headers=self.headers).status_code,403)
        self.db.agents*=2
        self.assertEqual(self.client.get('/api/agentes/contexto',headers=self.headers).status_code,503)
    def test_page_and_admin_route(self):
        self.assertEqual(self.client.get('/agente/'+self.db.token).status_code,200)
        self.assertEqual(self.client.get('/agente/'+str(uuid4())).status_code,404)
        self.assertEqual(self.client.get('/agente/propiedades').status_code,401)
    def test_docs_and_pagination(self):
        schema=self.client.get('/openapi.json').json()
        self.assertEqual(schema['paths']['/api/agentes/visitas']['get']['tags'],['Agentes'])
        self.assertEqual(self.client.get('/api/agentes/visitas?limit=61',headers=self.headers).status_code,422)
        self.assertEqual(self.client.get('/api/agentes/visitas?offset=1',headers=self.headers).json(),[])

    def test_contact_transition_and_history_counts(self):
        response=self.client.post('/api/agentes/visitas/1/contactar',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.db.rpc_calls[0][0],'ru_agente_contactar_visita')
        self.assertEqual(self.client.get('/api/agentes/visitas',headers=self.headers).json(),[])
        history=self.client.get('/api/agentes/visitas?estado=contactadas',headers=self.headers)
        self.assertEqual(history.json()[0]['id'],1)
        counts=self.client.get('/api/agentes/visitas/conteos',headers=self.headers)
        self.assertEqual(counts.json(),{'pendientes':0,'contactadas':1})
        self.assertEqual(self.client.post('/api/agentes/visitas/1/contactar',headers=self.headers).status_code,409)
    def test_contact_denies_wrong_specialty_and_missing_visit(self):
        for visit_id in (2,999):
            self.assertEqual(self.client.post(f'/api/agentes/visitas/{visit_id}/contactar',headers=self.headers).status_code,404)
        self.assertEqual(self.db.visits[1]['estados_visita']['nombre'],get_settings().initial_visit_state)
    def test_contact_requires_agent_token(self):
        response=self.client.post('/api/agentes/visitas/1/contactar')
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.db.rpc_calls,[])
    def test_contact_error_messages(self):
        for tag,expected in [('RU_AGENT_ACCESS',403),('RU_AGENT_PENDING',409),('RU_AGENT_STATE',503),('RU_AGENT_CONTACTED',409)]:
            self.db.rpc_error=APIError({'code':'P0001','message':tag,'details':None,'hint':None})
            response=self.client.post('/api/agentes/visitas/1/contactar',headers=self.headers)
            self.assertEqual(response.status_code,expected)
        self.db.rpc_error=APIError({'code':'PGRST202','message':'function absent','details':None,'hint':None})
        self.assertIn('05',self.client.post('/api/agentes/visitas/1/contactar',headers=self.headers).json()['detail'])
    def test_contact_preserves_commercial_and_date_fields(self):
        v=self.db.visits[0];v.update(fecha_cliente='2030-01-01',fecha_agente=None,fecha_acordada=None)
        original=deepcopy(v)
        self.client.post('/api/agentes/visitas/1/contactar',headers=self.headers)
        self.assertEqual(v['oportunidades'],original['oportunidades'])
        for key in ('fecha_cliente','fecha_agente','fecha_acordada'):self.assertEqual(v[key],original[key])
    def test_contacted_history_survives_commercial_closure(self):
        self.db.visits[0]['estados_visita']['nombre']='contactada'
        self.db.visits[0]['oportunidades']['resultado']='ganada'
        self.assertEqual(len(self.client.get('/api/agentes/visitas?estado=contactadas',headers=self.headers).json()),1)
    def test_invalid_view_rejected(self):
        self.assertEqual(self.client.get('/api/agentes/visitas?estado=cancelada',headers=self.headers).status_code,422)
