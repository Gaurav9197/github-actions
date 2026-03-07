import unittest
from app import app


class TestApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_status_endpoint(self):
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "running")
        self.assertIn("timestamp", data)


if __name__ == "__main__":
    unittest.main()
