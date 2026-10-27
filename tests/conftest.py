import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.services.auth_service import AuthService
from app.schemas.auth import UserRegister

# Each run owns a unique schema; public is never dropped.
from uuid import uuid4
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("Defina TEST_DATABASE_URL apontando para um banco dedicado com sufixo _test")
test_url = make_url(TEST_DATABASE_URL)
if not (test_url.database or "").endswith("_test") or test_url == make_url(settings.DATABASE_URL):
    raise RuntimeError("Testes exigem banco separado com sufixo _test")
TEST_SCHEMA = "msfinancas_test_" + uuid4().hex
admin_engine = create_engine(TEST_DATABASE_URL)
engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-csearch_path={TEST_SCHEMA}"})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, join_transaction_mode="create_savepoint")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{TEST_SCHEMA}"'))
    try:
        with engine.begin() as conn:
            cfg = Config("alembic.ini")
            cfg.attributes['connection'] = conn
            command.upgrade(cfg, 'head')
        yield
    finally:
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{TEST_SCHEMA}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    user_data = UserRegister(
        email="testuser@example.com",
        full_name="Mateus Rabelo",
        password="secretpassword123"
    )
    user, family = AuthService.register_user(db, user_data)
    return {"user": user, "family": family}


@pytest.fixture
def auth_headers(client, test_user):
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "testuser@example.com", "password": "secretpassword123"}
    )
    token = response.json()["access_token"]
    family_id = str(test_user["family"].id)
    return {
        "Authorization": f"Bearer {token}",
        "X-Family-Id": family_id
    }
