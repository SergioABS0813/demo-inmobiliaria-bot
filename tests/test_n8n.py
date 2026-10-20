from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

adapter_path = Path(__file__).resolve().parents[1] / 'n8n/adaptar_enviar_link.py'
if not adapter_path.is_file():
    raise unittest.SkipTest('Pruebas históricas del generador n8n retirado; no se genera ningún workflow en esta adaptación.')
spec = importlib.util.spec_from_file_location('link_adapter', adapter_path)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class LinkTests(unittest.TestCase):
    def test_only_link_bodies_change(self):
        source = {'nodes':[
            {'name':name,'type':'n8n-nodes-base.httpRequest','parameters':{'jsonBody':'old','url':'unchanged'},'credentials':{'reference':'keep'}}
            for name in ('enviar-link','enviar-link-1','other')
        ],'connections':{'preserved':True},'active':False}
        before = deepcopy(source)
        result = adapter.adapt(source)
        self.assertEqual(source,before)
        self.assertEqual(result['connections'], source['connections'])
        self.assertEqual(result['nodes'][2], source['nodes'][2])
        for node, old in zip(result['nodes'][:2], source['nodes'][:2]):
            body = json.loads(node['parameters']['jsonBody'][1:])
            self.assertEqual(body['interactive']['action']['parameters']['url'],'https://raizurbana.bestsolperu.com/inmuebles/{{ $json.token_uuid }}')
            self.assertIn("$('trigger_whatsapp')",body['recipient'])
            self.assertNotIn('pedido',node['parameters']['jsonBody'].lower())
            node['parameters']['jsonBody']=old['parameters']['jsonBody']
            self.assertEqual(node,old)

    def test_missing_node_fails_without_partial_export(self):
        with self.assertRaises(ValueError): adapter.adapt({'nodes':[]})
