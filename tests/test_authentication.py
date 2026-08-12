from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth_routes, routes as api_routes
from app.auth import token_hash
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    AuthenticationEvent,
    AuthenticationSession,
    User,
    UserAccessPass,
    Warehouse,
    WarehouseWorkstation,
    utcnow,
)
from app.models.enums import AuthenticationEventType, UserRole


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    app.dependency_overrides[auth_routes.get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def bootstrap(client, *, username: str = "admin", password: str = "Admin-pass-2026"):
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "username": username,
            "full_name": "Администратор WMS",
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def login(client, *, username: str = "admin", password: str = "Admin-pass-2026"):
    response = client.post(
        "/api/auth/login/password",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_password_login_cookie_logout_and_bearer_token(db, client):
    user = bootstrap(client)
    assert user["role"] == "admin"
    assert client.post(
        "/api/auth/bootstrap",
        json={
            "username": "second-admin",
            "full_name": "Второй администратор",
            "password": "Second-pass-2026",
        },
    ).status_code == 409

    result = login(client)
    assert result["authentication_method"] == "password"
    assert result["session_token"].startswith("WMS-SID.")
    assert client.get("/api/auth/me").json()["username"] == "admin"
    assert db.scalar(select(AuthenticationSession.token_hash)) == token_hash(
        result["session_token"]
    )
    assert result["session_token"] not in db.scalar(select(AuthenticationSession.token_hash))

    bearer_client = TestClient(app)
    bearer_me = bearer_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {result['session_token']}"},
    )
    assert bearer_me.status_code == 200
    assert bearer_me.json()["id"] == user["id"]

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    session = db.scalar(select(AuthenticationSession))
    assert session.revoked_at is not None


def test_failed_password_attempts_lock_user_and_are_audited(db, client):
    bootstrap(client)
    for _ in range(5):
        response = client.post(
            "/api/auth/login/password",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert response.status_code == 401

    user = db.scalar(select(User).where(User.username == "admin"))
    assert user.failed_login_count == 5
    assert user.locked_until is not None
    assert client.post(
        "/api/auth/login/password",
        json={"username": "admin", "password": "Admin-pass-2026"},
    ).status_code == 401
    assert db.scalar(
        select(func.count(AuthenticationEvent.id)).where(
            AuthenticationEvent.event_type == AuthenticationEventType.LOGIN_FAILED
        )
    ) == 6


def test_administrator_creates_scoped_user_and_workstation(db, client):
    bootstrap(client)
    login(client)
    warehouse = Warehouse(code="WH-AUTH", name="Склад авторизации")
    db.add(warehouse)
    db.commit()

    workstation_response = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-WH-AUTH-01",
            "name": "ТСД приёмки",
            "warehouse_id": warehouse.id,
            "pass_login_enabled": True,
        },
    )
    assert workstation_response.status_code == 200

    user_response = client.post(
        "/api/auth/admin/users",
        json={
            "username": "storekeeper",
            "full_name": "Кладовщик",
            "role": "warehouse_clerk",
            "password": "Store-pass-2026",
            "warehouse_ids": [warehouse.id],
            "default_warehouse_id": warehouse.id,
        },
    )
    assert user_response.status_code == 200
    assert user_response.json()["warehouse_codes"] == ["WH-AUTH"]
    assert user_response.json()["must_change_password"] is True

    assert client.get("/api/auth/admin/users").status_code == 200
    assert client.get("/api/auth/admin/workstations").json()[0]["warehouse_code"] == "WH-AUTH"


def test_access_pass_rotation_invalidates_old_code(db, client):
    bootstrap(client)
    login(client)
    warehouse = Warehouse(code="WH-PASS", name="Склад пропусков")
    db.add(warehouse)
    db.commit()
    workstation = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-PASS-01",
            "name": "Терминал пропусков",
            "warehouse_id": warehouse.id,
        },
    ).json()
    user = client.post(
        "/api/auth/admin/users",
        json={
            "username": "pass-user",
            "full_name": "Оператор по пропуску",
            "role": "warehouse_clerk",
            "password": "Access-pass-2026",
            "warehouse_ids": [warehouse.id],
            "default_warehouse_id": warehouse.id,
        },
    ).json()

    first = client.post(
        f"/api/auth/admin/users/{user['id']}/passes/issue",
        json={"workstation_code": workstation["code"], "expires_days": 30},
    ).json()
    second = client.post(
        f"/api/auth/admin/users/{user['id']}/passes/issue",
        json={"workstation_code": workstation["code"], "expires_days": 30},
    ).json()
    assert first["login_code"] != second["login_code"]
    assert first["qr_payload"] == first["code128_payload"] == first["login_code"]
    stored_passes = list(db.scalars(select(UserAccessPass).order_by(UserAccessPass.id)))
    assert stored_passes[0].revoked_at is not None
    assert stored_passes[0].token_hash == token_hash(first["login_code"])
    assert first["login_code"] not in {item.token_hash for item in stored_passes}

    old_login = client.post(
        "/api/auth/login/pass",
        json={
            "access_code": first["login_code"],
            "workstation_code": workstation["code"],
        },
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/auth/login/pass",
        json={
            "access_code": second["login_code"],
            "workstation_code": workstation["code"],
        },
    )
    assert new_login.status_code == 200
    assert new_login.json()["user"]["username"] == "pass-user"


def test_access_pass_rejects_wrong_workstation_and_expired_session(db, client):
    bootstrap(client)
    login(client)
    warehouse = Warehouse(code="WH-BOUND", name="Склад привязки")
    db.add(warehouse)
    db.commit()
    first_workstation = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-BOUND-01",
            "name": "Первый терминал",
            "warehouse_id": warehouse.id,
        },
    ).json()
    client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-BOUND-02",
            "name": "Второй терминал",
            "warehouse_id": warehouse.id,
        },
    )
    user = client.post(
        "/api/auth/admin/users",
        json={
            "username": "bounded-user",
            "full_name": "Привязанный оператор",
            "role": "warehouse_clerk",
            "password": "Bound-pass-2026",
            "warehouse_ids": [warehouse.id],
        },
    ).json()
    issued = client.post(
        f"/api/auth/admin/users/{user['id']}/passes/issue",
        json={"workstation_code": first_workstation["code"]},
    ).json()
    assert client.post(
        "/api/auth/login/pass",
        json={
            "access_code": issued["login_code"],
            "workstation_code": "TSD-BOUND-02",
        },
    ).status_code == 401

    password_login = login(client)
    session = db.scalar(
        select(AuthenticationSession).where(
            AuthenticationSession.uid == password_login["session_uid"]
        )
    )
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_temporary_password_must_change_and_workstation_requires_warehouse_access(db, client):
    bootstrap(client)
    login(client)
    own = Warehouse(code="WH-LOGIN", name="Склад рабочего места")
    foreign = Warehouse(code="WH-LOGIN-X", name="Чужое рабочее место")
    db.add_all([own, foreign])
    db.commit()
    own_workstation = client.post(
        "/api/auth/admin/workstations",
        json={"code": "TSD-LOGIN-01", "name": "Свой терминал", "warehouse_id": own.id},
    ).json()
    foreign_workstation = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-LOGIN-X",
            "name": "Чужой терминал",
            "warehouse_id": foreign.id,
        },
    ).json()
    user = client.post(
        "/api/auth/admin/users",
        json={
            "username": "temporary-user",
            "full_name": "Пользователь с временным паролем",
            "role": "warehouse_clerk",
            "password": "Temporary-pass-2026",
            "warehouse_ids": [own.id],
        },
    ).json()

    user_client = TestClient(app)
    assert user_client.post(
        "/api/auth/login/password",
        json={
            "username": "temporary-user",
            "password": "Temporary-pass-2026",
            "workstation_code": foreign_workstation["code"],
        },
    ).status_code == 403
    login(user_client, username="temporary-user", password="Temporary-pass-2026")
    assert user_client.post(
        "/api/auth/passes/issue",
        json={
            "workstation_code": own_workstation["code"],
            "current_password": "Temporary-pass-2026",
        },
    ).status_code == 403
    assert user_client.post(
        "/api/auth/password/change",
        json={
            "current_password": "Temporary-pass-2026",
            "new_password": "Permanent-pass-2026",
        },
    ).status_code == 204
    issued = user_client.post(
        f"/api/auth/passes/issue",
        json={
            "workstation_code": own_workstation["code"],
            "current_password": "Permanent-pass-2026",
        },
    )
    assert issued.status_code == 200
    assert client.put(
        f"/api/auth/admin/users/{user['id']}/warehouses",
        json={"warehouse_ids": []},
    ).status_code == 200
    assert TestClient(app).post(
        "/api/auth/login/pass",
        json={
            "access_code": issued.json()["login_code"],
            "workstation_code": own_workstation["code"],
        },
    ).status_code == 401


def test_enforcement_blocks_anonymous_role_and_foreign_warehouse(db, client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_enforcement_enabled=True,
        auth_session_hours=12,
    )
    assert client.get("/api/warehouses").status_code == 401

    bootstrap(client)
    login(client)
    own = Warehouse(code="WH-OWN", name="Доступный склад")
    foreign = Warehouse(code="WH-FOREIGN", name="Чужой склад")
    db.add_all([own, foreign])
    db.commit()
    user = client.post(
        "/api/auth/admin/users",
        json={
            "username": "scoped-user",
            "full_name": "Ограниченный кладовщик",
            "role": "warehouse_clerk",
            "password": "Scoped-pass-2026",
            "warehouse_ids": [own.id],
            "must_change_password": False,
        },
    ).json()
    assert user["warehouse_codes"] == ["WH-OWN"]

    scoped_client = TestClient(app)
    login(scoped_client, username="scoped-user", password="Scoped-pass-2026")
    assert scoped_client.get("/api/auth/admin/users").status_code == 403
    assert scoped_client.put(
        f"/api/warehouses/{own.id}",
        json={
            "name": "Недоступное изменение",
            "city": None,
            "timezone": "Europe/Moscow",
        },
    ).status_code == 403
    forbidden = scoped_client.post(
        "/api/logistic-tasks",
        json={
            "warehouse_code": foreign.code,
            "task_type": "move",
            "object_uid": "NOT-IMPORTANT",
            "actor": "scoped-user",
        },
    )
    assert forbidden.status_code == 403
    own_request = scoped_client.post(
        "/api/logistic-tasks",
        json={
            "warehouse_code": own.code,
            "task_type": "move",
            "object_uid": "NOT-FOUND",
            "actor": "scoped-user",
        },
    )
    assert own_request.status_code != 403


def test_legacy_user_api_is_removed_and_senior_cannot_issue_admin_pass(db, client):
    administrator = bootstrap(client)
    login(client)
    assert client.get("/api/users").status_code == 404
    assert client.post(
        "/api/users",
        json={
            "username": "legacy-user",
            "full_name": "Старый маршрут",
            "role": "warehouse_clerk",
        },
    ).status_code == 404

    warehouse = Warehouse(code="WH-SEC", name="Склад проверки прав")
    db.add(warehouse)
    db.commit()
    workstation = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-SEC-01",
            "name": "Терминал проверки прав",
            "warehouse_id": warehouse.id,
        },
    ).json()
    client.post(
        "/api/auth/admin/users",
        json={
            "username": "senior-user",
            "full_name": "Старший кладовщик",
            "role": "senior_clerk",
            "password": "Senior-pass-2026",
            "warehouse_ids": [warehouse.id],
            "must_change_password": False,
        },
    )

    senior_client = TestClient(app)
    login(senior_client, username="senior-user", password="Senior-pass-2026")
    response = senior_client.post(
        f"/api/auth/admin/users/{administrator['id']}/passes/issue",
        json={"workstation_code": workstation["code"]},
    )
    assert response.status_code == 403


def test_login_and_profile_pages_are_available(client):
    login_page = client.get("/login")
    profile_page = client.get("/profile")
    settings_page = client.get("/settings")

    assert login_page.status_code == 200
    assert 'id="passwordLogin"' in login_page.text
    assert 'id="passLogin"' in login_page.text
    assert profile_page.status_code == 200
    assert 'id="issuePassForm"' in profile_page.text
    assert 'id="passwordChangeForm"' in profile_page.text
    assert "/static/universal-auth.js" in profile_page.text
    assert settings_page.status_code == 200
    assert 'id="warehouseForm"' in settings_page.text
    assert 'id="userForm"' in settings_page.text
    assert 'id="workstationForm"' in settings_page.text
    assert 'id="equipmentForm"' in settings_page.text
    assert "/static/universal-settings.js" in settings_page.text


def test_administration_updates_warehouse_user_and_revokes_workstation_access(db, client):
    administrator = bootstrap(client)
    login(client)
    warehouse_response = client.post(
        "/api/warehouses",
        json={
            "code": "WH-ADMIN",
            "name": "Склад настроек",
            "city": "Москва",
            "timezone": "Europe/Moscow",
        },
    )
    assert warehouse_response.status_code == 200
    warehouse = warehouse_response.json()
    updated_warehouse = client.put(
        f"/api/warehouses/{warehouse['id']}",
        json={
            "name": "Главный склад настроек",
            "city": "Тверь",
            "timezone": "Europe/Moscow",
        },
    )
    assert updated_warehouse.status_code == 200
    assert updated_warehouse.json()["code"] == "WH-ADMIN"
    assert updated_warehouse.json()["city"] == "Тверь"

    worker = client.post(
        "/api/auth/admin/users",
        json={
            "username": "settings-worker",
            "full_name": "Кладовщик настроек",
            "role": "warehouse_clerk",
            "password": "Settings-pass-2026",
            "warehouse_ids": [warehouse["id"]],
            "default_warehouse_id": warehouse["id"],
            "must_change_password": False,
        },
    ).json()
    updated_worker = client.put(
        f"/api/auth/admin/users/{worker['id']}",
        json={
            "full_name": "Старший оператор настроек",
            "role": "senior_clerk",
            "is_active": True,
            "warehouse_ids": [warehouse["id"]],
            "default_warehouse_id": warehouse["id"],
        },
    )
    assert updated_worker.status_code == 200
    assert updated_worker.json()["role"] == "senior_clerk"
    assert updated_worker.json()["default_warehouse_id"] == warehouse["id"]
    assert updated_worker.json()["warehouse_codes"] == ["WH-ADMIN"]
    assert client.put(
        f"/api/auth/admin/users/{administrator['id']}",
        json={
            "full_name": "Отключённый администратор",
            "role": "warehouse_clerk",
            "is_active": False,
            "warehouse_ids": [],
        },
    ).status_code == 403

    workstation = client.post(
        "/api/auth/admin/workstations",
        json={
            "code": "TSD-ADMIN-01",
            "name": "Рабочее место настроек",
            "warehouse_id": warehouse["id"],
        },
    ).json()
    issued = client.post(
        f"/api/auth/admin/users/{worker['id']}/passes/issue",
        json={"workstation_code": workstation["code"]},
    ).json()
    pass_client = TestClient(app)
    assert pass_client.post(
        "/api/auth/login/pass",
        json={
            "access_code": issued["login_code"],
            "workstation_code": workstation["code"],
        },
    ).status_code == 200

    disabled = client.put(
        f"/api/auth/admin/workstations/{workstation['id']}",
        json={
            "name": workstation["name"],
            "warehouse_id": warehouse["id"],
            "pass_login_enabled": False,
            "is_active": False,
        },
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert pass_client.get("/api/auth/me").status_code == 401
    assert TestClient(app).post(
        "/api/auth/login/pass",
        json={
            "access_code": issued["login_code"],
            "workstation_code": workstation["code"],
        },
    ).status_code == 401
