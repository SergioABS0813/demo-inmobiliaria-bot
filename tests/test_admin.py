from copy import deepcopy
from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from pydantic import SecretStr, ValidationError
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.admin_schemas import PropertyWrite, ImageOrderIn
from app import admin_services as service


class Query:
    def __init__(self,db,table):self.db=db;self.table=table;self.filters={};self.mode='select';self.body=None;self.start=0;self.end=999;self.max=None;self.count=False
    def select(self,fields,count=None):self.count=bool(count);return self
    def eq(self,key,value):self.filters[key]=value;return self
    def order(self,*args,**kwargs):return self
    def range(self,start,end):self.start=start;self.end=end;return self
    def limit(self,n):self.max=n;return self
    def ilike(self,*args):return self
    def or_(self,*args):return self
    def insert(self,body):self.mode='insert';self.body=body;return self
    def update(self,body):self.mode='update';self.body=body;return self
    def delete(self):self.mode='delete';return self
    def upsert(self,body,**kwargs):self.mode='insert';self.body=body;return self
    def execute(self):
        self.db.queries.append((self.table,self.mode,deepcopy(self.body)))
        rows=self.db.tables[self.table];selected=[r for r in rows if all(r.get(k)==v for k,v in self.filters.items())]
        if self.mode=='insert':
            row={'id':max([r['id'] for r in rows],default=0)+1,**self.body};rows.append(row);selected=[row]
        elif self.mode=='update':
            for row in selected:row.update(self.body)
        elif self.mode=='delete':
            self.db.tables[self.table]=[r for r in rows if r not in selected]
        count=len(selected)
        selected=selected[self.start:self.end+1]
        if self.max is not None:selected=selected[:self.max]
        return SimpleNamespace(data=deepcopy(selected),count=count if self.count else None)


class Bucket:
    def __init__(self):self.uploaded=[];self.removed=[];self.fail_upload=False;self.fail_remove=False
    def upload(self,key,data,options):
        if self.fail_upload:raise OSError('transport error')
        self.uploaded.append((key,data,options))
    def get_public_url(self,key):return 'https://example.supabase.co/storage/v1/object/public/'+service.BUCKET+'/'+key
    def remove(self,keys):
        if self.fail_remove:raise OSError('storage error')
        self.removed.extend(keys)


class FakeDB:
    def __init__(self):
        self.queries=[];self.calls=[];self.fail_register=False;self.bucket=Bucket()
        self.storage=SimpleNamespace(from_=lambda bucket:self.bucket)
        self.tables={'propiedades':[{'id':1,'titulo':'Casa demo','disponible':True,'agente_id':None,'distrito_id':1}],
            'distritos':[{'id':1,'nombre':'Miraflores','activo':True},{'id':2,'nombre':'Barranco','activo':False}],
            'agentes':[{'id':1,'nombre':'Agente demo'}],'propiedad_imagenes':[], 'propiedad_archivos_pendientes':[]}
    def table(self,name):return Query(self,name)
    def rpc(self,name,args):
        self.calls.append((name,args))
        def execute():
            if name=='ru_admin_registrar_imagen':
                if self.fail_register:raise OSError('database error')
                row={'id':len(self.tables['propiedad_imagenes'])+1,'propiedad_id':args['p_propiedad_id'],'url':args['p_url'],'categoria':args['p_categoria'],'orden':1}
                self.tables['propiedad_imagenes'].append(row);return SimpleNamespace(data=row)
            if name=='ru_admin_retirar_imagen':
                self.tables['propiedad_imagenes']=[r for r in self.tables['propiedad_imagenes'] if r['id']!=args['p_imagen_id']]
                if args['p_object_key']:self.tables['propiedad_archivos_pendientes'].append({'id':1,'bucket':args['p_bucket'],'object_key':args['p_object_key']})
                return SimpleNamespace(data={'eliminada':True})
            if name=='ru_admin_ordenar_imagenes':return SimpleNamespace(data=self.tables['propiedad_imagenes'])
            raise AssertionError(name)
        return SimpleNamespace(execute=execute)


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB();app.dependency_overrides[get_db]=lambda:self.db
        self.settings=patch('app.admin_auth.get_settings',return_value=SimpleNamespace(admin_username='tester',admin_password=SecretStr('test-only-password-long-enough')))
        self.settings.start();self.client=TestClient(app,raise_server_exceptions=False)
        self.auth=('tester','test-only-password-long-enough');self.headers={'X-RU-Admin':'1'}
    def tearDown(self):self.settings.stop();app.dependency_overrides.clear()
    def png(self):
        output=BytesIO();Image.new('RGB',(4,4)).save(output,format='PNG');return output.getvalue()
    def request(self,method,path,**kwargs):
        return self.client.request(method,path,auth=self.auth,headers=self.headers,**kwargs)
    def test_page_and_reads_require_authentication(self):
        for path in ('/agente/propiedades','/api/agente/propiedades','/api/agente/opciones','/api/agente/propiedades/1/imagenes'):
            response=self.client.get(path);self.assertEqual(response.status_code,401,path)
        self.assertEqual(self.db.queries,[])
    def test_invalid_admin_password_rejected(self):
        self.assertEqual(self.client.get('/agente/propiedades',auth=('tester','incorrect')).status_code,401)
    def test_configured_password_has_no_artificial_minimum(self):
        with patch('app.admin_auth.get_settings',return_value=SimpleNamespace(admin_username='tester',admin_password=SecretStr('demo-test'))):
            self.assertEqual(self.client.get('/agente/propiedades',auth=('tester','demo-test')).status_code,200)
            self.assertEqual(self.client.get('/agente/propiedades',auth=('tester','wrong')).status_code,401)
    def test_unconfigured_panel_disabled(self):
        with patch('app.admin_auth.get_settings',return_value=SimpleNamespace(admin_username='tester',admin_password=None)):
            self.assertEqual(self.client.get('/agente/propiedades').status_code,503)
    def test_opportunity_token_does_not_authorize_admin(self):
        self.assertEqual(self.client.get('/api/agente/propiedades',headers={'X-Opportunity-Token':'00000000-0000-0000-0000-000000000001'}).status_code,401)
    def test_writes_require_custom_header(self):
        self.assertEqual(self.client.post('/api/agente/propiedades',auth=self.auth,json={'titulo':'Casa'}).status_code,403)
        params=self.client.get('/openapi.json').json()['paths']['/api/agente/propiedades']['post']['parameters']
        self.assertTrue(any(p['name']=='X-RU-Admin' and p['in']=='header' for p in params))
    def test_cross_origin_writes_rejected(self):
        response=self.client.post('/api/agente/propiedades',auth=self.auth,headers={**self.headers,'Origin':'https://attacker.example'},json={'titulo':'Casa'})
        self.assertEqual(response.status_code,403);self.assertEqual(self.db.queries,[])
    def test_https_proxy_origin_same_host_allowed(self):
        response=self.client.post('/api/agente/propiedades',auth=self.auth,headers={**self.headers,'Origin':'https://testserver'},json={'titulo':'Casa nueva'})
        self.assertEqual(response.status_code,201)
    def test_panel_template_not_served_from_static(self):
        self.assertEqual(self.client.get('/static/agente_propiedades.html').status_code,404)
        response=self.request('GET','/agente/propiedades');self.assertEqual(response.status_code,200)
        self.assertIn('Fotografías y planos',response.text);self.assertIn('blob:',response.headers['content-security-policy'])
    def test_create_defaults_to_unpublished(self):
        response=self.request('POST','/api/agente/propiedades',json={'titulo':'Casa nueva','precio':'123456.78','moneda':'USD'})
        self.assertEqual(response.status_code,201);self.assertFalse(response.json()['disponible'])
    def test_optional_fields_and_decimal_validation(self):
        self.assertIsNone(PropertyWrite(descripcion='  ').descripcion)
        for body in ({'precio':'-1'},{'area_total':0},{'cantidad_banos':-1},{'precio':'NaN'},{'cocheras':1.5},{'token_uuid':'bad'}):
            with self.assertRaises(ValidationError):PropertyWrite(**body)
    def test_missing_reference_rejected(self):
        self.assertEqual(self.request('POST','/api/agente/propiedades',json={'distrito_id':999}).status_code,422)
    def test_edit_preserves_existing_images(self):
        self.db.tables['propiedad_imagenes']=[{'id':9,'propiedad_id':1,'url':'https://external.example/a.jpg','orden':1}]
        before=deepcopy(self.db.tables['propiedad_imagenes'])
        response=self.request('PATCH','/api/agente/propiedades/1',json={'titulo':'Título actualizado'})
        self.assertEqual(response.status_code,200);self.assertEqual(self.db.tables['propiedad_imagenes'],before)
    def test_deactivation_does_not_delete_property(self):
        response=self.request('PATCH','/api/agente/propiedades/1/disponibilidad',json={'disponible':False})
        self.assertEqual(response.status_code,200);self.assertEqual(len(self.db.tables['propiedades']),1)
        self.assertFalse(self.db.tables['propiedades'][0]['disponible'])
        self.assertFalse(any(mode=='delete' and table=='propiedades' for table,mode,body in self.db.queries))
    def test_active_districts_prioritized(self):
        self.db.tables['distritos'].reverse()
        data=self.request('GET','/api/agente/opciones').json();self.assertTrue(data['distritos'][0]['activo'])
        self.assertNotIn('telefono',str(data['agentes']))
    def test_forged_and_oversized_images_rejected(self):
        for data in (b'not an image', b'\x89PNG\r\n\x1a\n<script>', b'x'*(service.MAX_FILE+1)):
            with self.assertRaises(HTTPException):service.validate_image(data,'image/png')
    def test_real_image_and_mime_checked(self):
        self.assertEqual(service.validate_image(self.png(),'image/png'),('png','image/png'))
        with self.assertRaises(HTTPException):service.validate_image(self.png(),'image/jpeg')
        for fmt,mime,extension in (('JPEG','image/jpeg','jpg'),('WEBP','image/webp','webp')):
            output=BytesIO();Image.new('RGB',(4,4)).save(output,format=fmt)
            self.assertEqual(service.validate_image(output.getvalue(),mime),(extension,mime))
    def test_paths_are_unique_and_categories_are_siblings(self):
        paths=[service.storage_key(1,c,'../../sala.png','png') for c in ('vista_1','vista_2','plano')]
        self.assertEqual({p.split('/')[1] for p in paths},{'vista_1','vista_2','plano'})
        self.assertTrue(all(p.startswith('propiedad_1/') and len(p.split('/'))==3 for p in paths))
        self.assertNotEqual(paths[0],service.storage_key(1,'vista_1','../../sala.png','png'))
    def test_upload_generates_row_and_public_url(self):
        response=self.request('POST','/api/agente/propiedades/1/imagenes',data={'categoria':'plano'},files=[('files',('plano.png',self.png(),'image/png'))])
        self.assertEqual(response.status_code,200)
        row=response.json()['imagenes'][0];self.assertEqual(row['categoria'],'plano')
        self.assertIn('/propiedad_1/plano/',row['url']);self.assertEqual(response.json()['errores'],[])
    def test_invalid_batch_does_not_start_upload(self):
        response=self.request('POST','/api/agente/propiedades/1/imagenes',data={'categoria':'vista_1'},files=[('files',('ok.png',self.png(),'image/png')),('files',('bad.jpg',b'bad','image/jpeg'))])
        self.assertEqual(response.status_code,422);self.assertEqual(self.db.bucket.uploaded,[])
    def test_upload_failure_compensates_storage(self):
        self.db.fail_register=True
        row,error=service.upload_one(self.db,1,'vista_1','foto.png',self.png(),'png','image/png')
        self.assertIsNone(row);self.assertTrue(error);self.assertEqual(len(self.db.bucket.removed),1)
    def test_failed_compensation_is_queued(self):
        self.db.fail_register=True;self.db.bucket.fail_remove=True
        service.upload_one(self.db,1,'vista_1','foto.png',self.png(),'png','image/png')
        self.assertEqual(len(self.db.tables['propiedad_archivos_pendientes']),1)
    def test_removal_failure_keeps_durable_queue(self):
        key='propiedad_1/vista_1/foto.jpg';url=self.db.bucket.get_public_url(key)
        self.db.tables['propiedad_imagenes']=[{'id':9,'propiedad_id':1,'url':url}];self.db.bucket.fail_remove=True
        response=self.request('DELETE','/api/agente/propiedades/1/imagenes/9')
        self.assertEqual(response.status_code,200);self.assertEqual(self.db.tables['propiedad_imagenes'],[])
        self.assertEqual(response.json()['pendientes_revisados'],1)
        self.db.bucket.fail_remove=False
        result=service.run_cleanup(self.db);self.assertEqual(result['eliminados'],1)
        self.assertEqual(self.db.tables['propiedad_archivos_pendientes'],[])
    def test_external_files_never_deleted(self):
        self.db.tables['propiedad_imagenes']=[{'id':9,'propiedad_id':1,'url':'https://external.example/photo.jpg'}]
        response=self.request('DELETE','/api/agente/propiedades/1/imagenes/9')
        self.assertTrue(response.json()['archivo_externo_conservado']);self.assertEqual(self.db.bucket.removed,[])
    def test_file_cannot_be_deleted_through_wrong_property(self):
        self.db.tables['propiedad_imagenes']=[{'id':9,'propiedad_id':2,'url':'https://external.example/a.jpg'}]
        self.assertEqual(self.request('DELETE','/api/agente/propiedades/1/imagenes/9').status_code,404)
        self.assertEqual(len(self.db.tables['propiedad_imagenes']),1)
    def test_storage_path_ownership(self):
        with patch('app.admin_services.get_settings',return_value=SimpleNamespace(supabase_url='https://example.supabase.co')):
            self.assertIsNone(service.owned_storage_key(self.db.bucket.get_public_url('propiedad_2/vista_1/a.jpg'),1))
            self.assertIsNone(service.owned_storage_key(self.db.bucket.get_public_url('propiedad_1/vista_1/../a.jpg'),1))
            self.assertIsNone(service.owned_storage_key('https://other.example/storage/v1/object/public/'+service.BUCKET+'/propiedad_1/plano/a.png',1))
    def test_reorder_contract_and_input_validation(self):
        for ids in ([1,1],[-1]):
            with self.assertRaises(ValidationError):ImageOrderIn(ids=ids)
        response=self.request('PUT','/api/agente/propiedades/1/imagenes/orden',json={'ids':[3,2,1]})
        self.assertEqual(response.status_code,200);self.assertEqual(self.db.calls[-1],('ru_admin_ordenar_imagenes',{'p_propiedad_id':1,'p_ids':[3,2,1]}))
    def test_no_property_delete_endpoint(self):
        self.assertEqual(self.request('DELETE','/api/agente/propiedades/1').status_code,405)
    def test_panel_controls_match_script_and_schema(self):
        class Controls(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.names=set()
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if attrs.get('id'):self.ids.append(attrs['id'])
                if tag in ('input','select','textarea') and attrs.get('name') not in (None,'q'):self.names.add(attrs['name'])
        root=Path(__file__).resolve().parents[1]
        controls=Controls();controls.feed((root/'app/templates/agente_propiedades.html').read_text(encoding='utf-8'))
        self.assertEqual(len(controls.ids),len(set(controls.ids)))
        script=(root/'static/js/admin.js').read_text(encoding='utf-8')
        for referenced in re.findall(r"\$\('([^']+)'\)",script):self.assertIn(referenced,controls.ids)
        self.assertEqual(controls.names,set(PropertyWrite.model_fields))
