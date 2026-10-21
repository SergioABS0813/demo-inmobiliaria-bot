import unittest
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.config import get_settings


class Query:
    def __init__(self, db, table):
        self.db=db;self.table=table;self.filters={};self.span=None
    def select(self,*args,**kwargs):return self
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
            rows=[v for v in self.db.visits if v['propiedades']['tipo_inmueble']==self.filters['propiedades.tipo_inmueble'] and v['estados_visita']['nombre']==self.filters['estados_visita.nombre'] and v['oportunidades']['resultado'] is None and v['oportunidades']['fecha_cierre'] is None]
            rows=rows[self.span[0]:self.span[1]+1]
        return SimpleNamespace(data=deepcopy(rows))


class Agents(unittest.TestCase):
    def setUp(self):
        self.db=SimpleNamespace(token=str(uuid4()),calls=[],agents=[{'id':1,'nombre':'Ana','especialidad':'Departamento'}],visits=[])
        self.db.table=lambda table:Query(self.db,table)
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
