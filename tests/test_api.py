import os
import unittest
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DISABLED", "true")  # bypass auth for tests

from apps.api.main import app  # noqa: E402


class FakeDB:
    def __init__(self):
        self.data = {}
        self._id = 1

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self._id
            self._id += 1
        self.data.setdefault(type(obj).__name__, {})[obj.id] = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def get(self, model, id_):
        return self.data.get(model.__name__, {}).get(id_)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")

    def test_books_list_ok(self):
        r = self.client.get("/v1/books")
        self.assertEqual(r.status_code, 200)
        self.assertIn("items", r.json())

    def test_translate_and_qa_with_overrides(self):
        # Prepare fake DB with Book/Paragraph
        from apps.api.models.models import Book, Paragraph
        from apps.api import main as api_main
        from apps.api.services import llm

        fake = FakeDB()
        b = Book(id=1, title="テスト本", author="著者")
        p = Paragraph(id=10, book_id=1, idx=0, text="昔々あるところに…")
        fake.add(b)
        fake.add(p)

        def override_db():
            yield fake

        # Override dependencies
        api_main.app.dependency_overrides[api_main.v1.books.get_current_user_optional] = lambda: {"uid": "u"}
        api_main.app.dependency_overrides[api_main.v1.translate.get_current_user] = lambda: {"uid": "u"}
        api_main.app.dependency_overrides[api_main.v1.qa.get_current_user] = lambda: {"uid": "u"}
        api_main.app.dependency_overrides[api_main.v1.translate.get_db] = override_db
        api_main.app.dependency_overrides[api_main.v1.qa.get_db] = override_db

        # Monkeypatch LLM services
        orig_tr = llm.translate_paragraph
        orig_qa = llm.answer_question
        llm.translate_paragraph = lambda title, para: (f"{para} ←現代語訳", 5)
        llm.answer_question = lambda title, q: ("回答: " + q, 7)

        try:
            r = self.client.post("/v1/translate", json={"book_id": 1, "para_id": 10})
            self.assertEqual(r.status_code, 200)
            self.assertIn("translation", r.json())

            r2 = self.client.post("/v1/qa", json={"book_id": 1, "question": "背景は？"})
            self.assertEqual(r2.status_code, 200)
            self.assertIn("answer", r2.json())
        finally:
            llm.translate_paragraph = orig_tr
            llm.answer_question = orig_qa


if __name__ == "__main__":
    unittest.main()
