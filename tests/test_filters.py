import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db


class Query:
    def __init__(self, db, table):self.db=db;self.table=table;self.start=0;self.end=499
    def select(self, fields):return self
    def order(self, field):return self
    def range(self,start,end):self.start=start;self.end=end;return self
    def execute(self):return SimpleNamespace(data=self.db.rows[self.table][self.start:self.end+1])


class FilterOptionsTests(unittest.TestCase):
    def setUp(self):
        self.db=SimpleNamespace(rows={'propiedades':[],'distritos':[]})
        self.db.table=lambda name:Query(self.db,name)
        app.dependency_overrides[get_db]=lambda:self.db
        self.auth=patch('app.main.require_opportunity',return_value={'id':1})
        self.auth.start();self.client=TestClient(app)
    def tearDown(self):
        self.auth.stop();app.dependency_overrides.clear()
    def fetch(self):return self.client.get('/api/propiedades/filtros',headers={'X-Opportunity-Token':str(uuid4())})
    def test_districts_do_not_require_available_properties(self):
        self.db.rows['distritos']=[{'id':2,'nombre':'Surco'},{'id':1,'nombre':'Miraflores'}]
        response=self.fetch()
        self.assertEqual(response.status_code,200)
        self.assertEqual([d['nombre'] for d in response.json()['distritos']],['Miraflores','Surco'])
    def test_types_and_operations_are_real_distinct_values(self):
        self.db.rows['propiedades']=[
            {'id':1,'tipo_inmueble':'Departamento','tipo_operacion':'Venta','moneda':'USD'},
            {'id':2,'tipo_inmueble':'Departamento','tipo_operacion':'Alquiler','moneda':'PEN'},
            {'id':3,'tipo_inmueble':'Casa','tipo_operacion':None,'moneda':' '},
        ]
        data=self.fetch().json()
        self.assertEqual(data['tipos'],['Casa','Departamento'])
        self.assertEqual(data['operaciones'],['Alquiler','Venta'])
        self.assertEqual(data['monedas'],['PEN','USD'])
    def test_pagination_does_not_truncate_registry(self):
        self.db.rows['distritos']=[{'id':i,'nombre':f'Distrito {i:04}'} for i in range(1003)]
        self.assertEqual(len(self.fetch().json()['distritos']),1003)
