"""Guardas de configuração: nunca criar conexão com senha implícita ou placeholder."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class DatabaseConfigTests(unittest.TestCase):
    def backend(self, env):
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"), patch("sqlalchemy.create_engine") as factory, patch("sqlalchemy.orm.sessionmaker"):
            result = runpy.run_path(str(ROOT / "backend/app/database.py"))
            return result, factory

    def etl(self, env):
        from etl.config.settings import default_engine
        with patch.dict(os.environ, env, clear=True), patch("etl.config.settings.load_dotenv"), patch("etl.config.settings.create_engine") as factory:
            default_engine()
            return factory

    def test_backend_rejects_missing_password(self):
        with self.assertRaises(RuntimeError):
            self.backend({})

    def test_backend_rejects_empty_and_placeholder(self):
        for password in ("", "SUBSTITUA_POR_UMA_SENHA_LOCAL"):
            with self.assertRaises(RuntimeError):
                self.backend({"POSTGRES_PASSWORD": password})

    def test_backend_passes_explicit_password_to_driver(self):
        _, factory = self.backend({"POSTGRES_PASSWORD": "test-only-not-a-real-secret"})
        self.assertEqual(factory.call_args.args[0].password, "test-only-not-a-real-secret")

    def test_etl_rejects_missing_password(self):
        with self.assertRaises(RuntimeError):
            self.etl({})

    def test_etl_rejects_empty_and_placeholder(self):
        for password in ("", "SUBSTITUA_POR_UMA_SENHA_LOCAL"):
            with self.assertRaises(RuntimeError):
                self.etl({"POSTGRES_PASSWORD": password})

    def test_etl_accepts_explicit_password(self):
        factory = self.etl({"POSTGRES_PASSWORD": "test-only-not-a-real-secret"})
        self.assertEqual(factory.call_args.args[0].password, "test-only-not-a-real-secret")

    def test_etl_preserves_explicit_url_alternative(self):
        factory = self.etl({"ETL_DATABASE_URL": "postgresql+psycopg2://example.invalid/demo"})
        self.assertEqual(factory.call_args.args[0], "postgresql+psycopg2://example.invalid/demo")
