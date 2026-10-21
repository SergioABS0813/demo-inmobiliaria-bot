import re
import unittest
from fastapi.testclient import TestClient
from app.main import app


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_openapi_contains_api_and_visit_schema(self):
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn('/api/visitas', schema['paths'])
        self.assertIn('post', schema['paths']['/api/visitas'])
        self.assertIn('VisitIn', schema['components']['schemas'])
        self.assertTrue(all(path.startswith('/api/') or path == '/agente/{token_uuid}' for path in schema['paths']))
        parameters = schema['paths']['/api/lead/contexto']['get']['parameters']
        self.assertTrue(any(p['name']=='X-Lead-Token' and p['in']=='header' for p in parameters))
        self.assertTrue(any(p['name']=='X-Opportunity-Token' and p['in']=='header' for p in parameters))
        self.assertIn('/api/visitas/actual',schema['paths'])

    def test_documentation_assets_and_inline_scripts_are_allowed(self):
        for path in ('/docs', '/redoc'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('/openapi.json', response.text)
            csp = response.headers['content-security-policy']
            self.assertIn('https://cdn.jsdelivr.net', csp)
            nonces = re.findall(r'<script nonce="([^"]+)"', response.text)
            self.assertTrue(nonces)
            self.assertEqual(len(set(nonces)), 1)
            self.assertIn(f"'nonce-{nonces[0]}'", csp)
            script_policy = next(p for p in csp.split(';') if 'script-src' in p)
            self.assertNotIn('unsafe-inline', script_policy)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(int(response.headers['content-length']), len(response.content))

    def test_nonce_is_not_reused(self):
        first = self.client.get('/docs').headers['content-security-policy']
        second = self.client.get('/docs').headers['content-security-policy']
        self.assertNotEqual(first, second)

    def test_site_keeps_original_policy(self):
        for path in ('/', '/inmuebles/example', '/api/health', '/openapi.json'):
            csp = self.client.get(path).headers['content-security-policy']
            self.assertNotIn('cdn.jsdelivr.net', csp)
            self.assertNotIn('unsafe-inline', csp)
            self.assertNotIn('nonce-', csp)
