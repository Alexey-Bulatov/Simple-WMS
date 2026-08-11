import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.entities import (
    AuthenticationEvent,
    AuthenticationSession,
    Location,
    LogisticInventory,
    LogisticShipment,
    LogisticTask,
    LogisticTransfer,
    LogisticUnit,
    StockPosition,
    StockReservation,
    StockReservationRequest,
    User,
    UserAccessPass,
    UserWarehouseAccess,
    Warehouse,
    WarehouseWorkstation,
    utcnow,
)
from app.models.enums import (
    AuthenticationEventType,
    AuthenticationMethod,
    UserRole,
)
from app.schemas import (
    AuthenticationAdminUserCreate,
    AuthenticationAdminPasswordResetRequest,
    AuthenticationBootstrapRequest,
    AuthenticationPassLoginRequest,
    AuthenticationPasswordChangeRequest,
    AuthenticationPasswordLoginRequest,
    UserAccessPassIssueRequest,
    UserWarehouseAssignmentRequest,
    WarehouseWorkstationCreate,
)


PASSWORD_ALGORITHM = "scrypt"
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_DKLEN = 32
SESSION_TOKEN_PREFIX = "WMS-SID"
ACCESS_PASS_PREFIX = "WMS-PASS"


@dataclass(frozen=True)
class AuthenticationContext:
    user: User
    session: AuthenticationSession


def _unauthorized(message: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(message: str = "operation is not permitted") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _encode_component(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_component(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        dklen=PASSWORD_DKLEN,
    )
    return (
        f"{PASSWORD_ALGORITHM}${PASSWORD_N}${PASSWORD_R}${PASSWORD_P}$"
        f"{_encode_component(salt)}${_encode_component(digest)}"
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        encoded = hash_password("invalid-password-placeholder")
    try:
        algorithm, n_value, r_value, p_value, salt_value, digest_value = encoded.split("$")
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = _decode_component(salt_value)
        expected = _decode_component(digest_value)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_value),
            r=int(r_value),
            p=int(p_value),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_client_data(request: Request) -> tuple[str | None, str | None]:
    client_ip = request.client.host if request.client is not None else None
    user_agent = request.headers.get("user-agent")
    return client_ip, user_agent[:300] if user_agent else None


def add_authentication_event(
    db: Session,
    *,
    event_type: AuthenticationEventType,
    succeeded: bool,
    request: Request,
    user: User | None = None,
    username: str | None = None,
    authentication_method: AuthenticationMethod | None = None,
    session_uid: str | None = None,
    workstation_code: str | None = None,
    reason: str | None = None,
) -> AuthenticationEvent:
    client_ip, user_agent = request_client_data(request)
    event = AuthenticationEvent(
        event_type=event_type,
        authentication_method=authentication_method,
        username=username or (user.username if user else None),
        user_id=user.id if user else None,
        session_uid=session_uid,
        workstation_code=workstation_code,
        client_ip=client_ip,
        user_agent=user_agent,
        succeeded=succeeded,
        reason=reason,
    )
    db.add(event)
    return event


def user_payload(db: Session, user: User) -> dict:
    accesses = list(
        db.scalars(
            select(UserWarehouseAccess)
            .where(UserWarehouseAccess.user_id == user.id)
            .order_by(UserWarehouseAccess.is_default.desc(), UserWarehouseAccess.id)
        )
    )
    warehouses = {
        warehouse.id: warehouse
        for warehouse in db.scalars(
            select(Warehouse).where(
                Warehouse.id.in_([access.warehouse_id for access in accesses])
            )
        )
    } if accesses else {}
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "password_changed_at": user.password_changed_at,
        "last_login_at": user.last_login_at,
        "locked_until": user.locked_until,
        "warehouse_ids": [access.warehouse_id for access in accesses],
        "warehouse_codes": [
            warehouses[access.warehouse_id].code
            for access in accesses
            if access.warehouse_id in warehouses
        ],
    }


def _workstation_by_code(db: Session, code: str | None) -> WarehouseWorkstation | None:
    if code is None:
        return None
    workstation = db.scalar(
        select(WarehouseWorkstation).where(WarehouseWorkstation.code == code.strip().upper())
    )
    if workstation is None or not workstation.is_active:
        raise _forbidden("active workstation is required")
    return workstation


def _user_has_warehouse_access(db: Session, user: User, warehouse_id: int) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    return db.scalar(
        select(UserWarehouseAccess.id).where(
            UserWarehouseAccess.user_id == user.id,
            UserWarehouseAccess.warehouse_id == warehouse_id,
        )
    ) is not None


def _create_session(
    db: Session,
    *,
    user: User,
    method: AuthenticationMethod,
    request: Request,
    workstation: WarehouseWorkstation | None,
    settings: Settings,
) -> tuple[AuthenticationSession, str]:
    session_uid = f"SES-{secrets.token_hex(10).upper()}"
    secret = secrets.token_urlsafe(32)
    raw_token = f"{SESSION_TOKEN_PREFIX}.{session_uid}.{secret}"
    client_ip, user_agent = request_client_data(request)
    now = utcnow()
    session = AuthenticationSession(
        uid=session_uid,
        user_id=user.id,
        token_hash=token_hash(raw_token),
        authentication_method=method,
        workstation_id=workstation.id if workstation else None,
        client_ip=client_ip,
        user_agent=user_agent,
        created_at=now,
        expires_at=now + timedelta(hours=settings.auth_session_hours),
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return session, raw_token


def bootstrap_administrator(
    db: Session,
    payload: AuthenticationBootstrapRequest,
    request: Request,
    settings: Settings,
) -> User:
    configured_token = settings.auth_bootstrap_token
    client_ip, _ = request_client_data(request)
    if configured_token:
        if not payload.bootstrap_token or not hmac.compare_digest(
            payload.bootstrap_token,
            configured_token,
        ):
            raise _forbidden("invalid bootstrap token")
    elif client_ip not in {"127.0.0.1", "::1", "testclient"}:
        raise _forbidden("bootstrap without a token is allowed only locally")
    configured_user = db.scalar(
        select(User.id).where(User.password_hash.is_not(None)).limit(1)
    )
    if configured_user is not None:
        raise _conflict("initial administrator is already configured")
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None:
        user = User(
            username=payload.username,
            full_name=payload.full_name,
            role=UserRole.ADMIN,
        )
        db.add(user)
    elif user.password_hash is not None:
        raise _conflict("initial administrator is already configured")
    user.full_name = payload.full_name
    user.role = UserRole.ADMIN
    user.password_hash = hash_password(payload.password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


def authenticate_with_password(
    db: Session,
    payload: AuthenticationPasswordLoginRequest,
    request: Request,
    settings: Settings,
) -> tuple[User, AuthenticationSession, str, WarehouseWorkstation | None]:
    user = db.scalar(
        select(User)
        .where(User.username == payload.username)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    now = utcnow()
    locked_until = _as_utc(user.locked_until) if user else None
    password_valid = verify_password(payload.password, user.password_hash if user else None)
    if (
        user is None
        or not user.is_active
        or locked_until is not None and locked_until > now
        or not password_valid
    ):
        reason = "invalid_credentials"
        if user is not None:
            if locked_until is not None and locked_until > now:
                reason = "user_locked"
            elif not user.is_active:
                reason = "user_inactive"
            else:
                user.failed_login_count += 1
                if user.failed_login_count >= settings.auth_lock_threshold:
                    user.locked_until = now + timedelta(minutes=settings.auth_lock_minutes)
                    reason = "failure_limit_reached"
        add_authentication_event(
            db,
            event_type=AuthenticationEventType.LOGIN_FAILED,
            succeeded=False,
            request=request,
            user=user,
            username=payload.username,
            authentication_method=AuthenticationMethod.PASSWORD,
            workstation_code=payload.workstation_code,
            reason=reason,
        )
        db.commit()
        raise _unauthorized("invalid username or password")

    workstation = _workstation_by_code(db, payload.workstation_code)
    if workstation is not None and not _user_has_warehouse_access(
        db,
        user,
        workstation.warehouse_id,
    ):
        add_authentication_event(
            db,
            event_type=AuthenticationEventType.LOGIN_FAILED,
            succeeded=False,
            request=request,
            user=user,
            authentication_method=AuthenticationMethod.PASSWORD,
            workstation_code=workstation.code,
            reason="workstation_warehouse_unavailable",
        )
        db.commit()
        raise _forbidden("workstation belongs to an unavailable warehouse")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session, raw_token = _create_session(
        db,
        user=user,
        method=AuthenticationMethod.PASSWORD,
        request=request,
        workstation=workstation,
        settings=settings,
    )
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.LOGIN_SUCCEEDED,
        succeeded=True,
        request=request,
        user=user,
        authentication_method=AuthenticationMethod.PASSWORD,
        session_uid=session.uid,
        workstation_code=workstation.code if workstation else None,
    )
    db.commit()
    db.refresh(user)
    db.refresh(session)
    return user, session, raw_token, workstation


def authenticate_with_access_pass(
    db: Session,
    payload: AuthenticationPassLoginRequest,
    request: Request,
    settings: Settings,
) -> tuple[User, AuthenticationSession, str, WarehouseWorkstation]:
    pass_hash = token_hash(payload.access_code)
    access_pass = db.scalar(
        select(UserAccessPass)
        .where(UserAccessPass.token_hash == pass_hash)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    workstation = db.scalar(
        select(WarehouseWorkstation).where(
            WarehouseWorkstation.code == payload.workstation_code
        )
    )
    user = db.get(User, access_pass.user_id) if access_pass else None
    now = utcnow()
    expires_at = _as_utc(access_pass.expires_at) if access_pass else None
    valid = (
        access_pass is not None
        and user is not None
        and user.is_active
        and access_pass.revoked_at is None
        and (expires_at is None or expires_at > now)
        and workstation is not None
        and workstation.is_active
        and workstation.pass_login_enabled
        and access_pass.workstation_id == workstation.id
        and _user_has_warehouse_access(db, user, workstation.warehouse_id)
        and (_as_utc(user.locked_until) is None or _as_utc(user.locked_until) <= now)
    )
    if not valid:
        add_authentication_event(
            db,
            event_type=AuthenticationEventType.LOGIN_FAILED,
            succeeded=False,
            request=request,
            user=user,
            authentication_method=AuthenticationMethod.ACCESS_PASS,
            workstation_code=payload.workstation_code,
            reason="invalid_or_revoked_access_pass",
        )
        db.commit()
        raise _unauthorized("invalid access pass")
    session, raw_token = _create_session(
        db,
        user=user,
        method=AuthenticationMethod.ACCESS_PASS,
        request=request,
        workstation=workstation,
        settings=settings,
    )
    access_pass.last_used_at = now
    user.last_login_at = now
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.LOGIN_SUCCEEDED,
        succeeded=True,
        request=request,
        user=user,
        authentication_method=AuthenticationMethod.ACCESS_PASS,
        session_uid=session.uid,
        workstation_code=workstation.code,
    )
    db.commit()
    db.refresh(session)
    return user, session, raw_token, workstation


def _raw_session_token(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(settings.auth_cookie_name)


def authentication_context(
    request: Request,
    db: Session,
    settings: Settings,
) -> AuthenticationContext:
    raw_token = _raw_session_token(request, settings)
    if not raw_token:
        raise _unauthorized()
    parts = raw_token.split(".")
    if len(parts) != 3 or parts[0] != SESSION_TOKEN_PREFIX:
        raise _unauthorized("invalid session")
    session = db.scalar(
        select(AuthenticationSession).where(AuthenticationSession.uid == parts[1])
    )
    now = utcnow()
    if (
        session is None
        or session.revoked_at is not None
        or _as_utc(session.expires_at) <= now
        or not hmac.compare_digest(session.token_hash, token_hash(raw_token))
    ):
        raise _unauthorized("session expired or revoked")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("user is inactive")
    locked_until = _as_utc(user.locked_until)
    if locked_until is not None and locked_until > now:
        raise _unauthorized("user is locked")
    if now - _as_utc(session.last_seen_at) >= timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return AuthenticationContext(user=user, session=session)


def require_authentication_context(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthenticationContext:
    return authentication_context(request, db, settings)


def require_administrator(
    context: AuthenticationContext = Depends(require_authentication_context),
) -> AuthenticationContext:
    if context.user.role != UserRole.ADMIN:
        raise _forbidden("administrator role is required")
    if context.user.must_change_password:
        raise _forbidden("password change is required")
    return context


def require_pass_issuer(
    context: AuthenticationContext = Depends(require_authentication_context),
) -> AuthenticationContext:
    if context.user.role not in {
        UserRole.ADMIN,
        UserRole.WAREHOUSE_MANAGER,
        UserRole.SENIOR_CLERK,
    }:
        raise _forbidden("senior warehouse role is required")
    if context.user.must_change_password:
        raise _forbidden("password change is required")
    return context


def require_security_reader(
    context: AuthenticationContext = Depends(require_authentication_context),
) -> AuthenticationContext:
    if context.user.role not in {UserRole.ADMIN, UserRole.AUDITOR}:
        raise _forbidden("security audit permission is required")
    if context.user.must_change_password:
        raise _forbidden("password change is required")
    return context


ROLE_MUTATION_ROOTS: dict[UserRole, set[str]] = {
    UserRole.PRODUCTION_OPERATOR: {"logistic-units", "logistic-tasks"},
    UserRole.RECEIVING_CLERK: {
        "logistic-units",
        "logistic-inventories",
        "logistic-tasks",
    },
    UserRole.WAREHOUSE_CLERK: {
        "logistic-units",
        "logistic-shipments",
        "logistic-transfers",
        "logistic-inventories",
        "logistic-tasks",
        "stock-reservations",
        "stock-reservation-requests",
    },
    UserRole.SHIPPING_OPERATOR: {
        "logistic-units",
        "logistic-shipments",
        "logistic-transfers",
        "logistic-tasks",
        "stock-reservations",
        "stock-reservation-requests",
    },
    UserRole.SENIOR_CLERK: {
        "logistic-units",
        "logistic-shipments",
        "logistic-transfers",
        "logistic-inventories",
        "logistic-tasks",
        "stock-reservations",
        "stock-reservation-requests",
        "stock-documents",
        "locations",
    },
    UserRole.WAREHOUSE_MANAGER: {
        "maps",
        "logistic-units",
        "logistic-shipments",
        "logistic-transfers",
        "logistic-inventories",
        "logistic-tasks",
        "stock-reservations",
        "stock-reservation-requests",
        "stock-documents",
        "locations",
        "zones",
        "aisles",
        "racks",
        "rack-sections",
        "rack-levels",
    },
    UserRole.AUDITOR: set(),
    UserRole.INTEGRATION: set(),
}


async def _request_json(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return {}
    try:
        payload = await request.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _warehouse_id_for_unit(db: Session, uid: str) -> int | None:
    unit = db.scalar(select(LogisticUnit).where(LogisticUnit.uid == uid.strip().upper()))
    if unit is None:
        return None
    visited: set[int] = set()
    while unit.parent_unit_id is not None and unit.id not in visited:
        visited.add(unit.id)
        parent = db.get(LogisticUnit, unit.parent_unit_id)
        if parent is None:
            break
        unit = parent
    location = db.get(Location, unit.current_location_id) if unit.current_location_id else None
    return location.warehouse_id if location else None


def _warehouse_id_for_position(db: Session, position: StockPosition) -> int | None:
    if position.logistic_unit_id is not None:
        unit = db.get(LogisticUnit, position.logistic_unit_id)
        return _warehouse_id_for_unit(db, unit.uid) if unit else None
    location = db.get(Location, position.location_id) if position.location_id else None
    return location.warehouse_id if location else None


async def request_warehouse_ids(db: Session, request: Request) -> set[int]:
    result: set[int] = set()
    payload = await _request_json(request)
    for key in ("warehouse_id", "source_warehouse_id", "destination_warehouse_id"):
        value = payload.get(key)
        if isinstance(value, int):
            result.add(value)
    warehouse_codes = {
        value.strip().upper()
        for key in (
            "warehouse_code",
            "source_warehouse_code",
            "destination_warehouse_code",
        )
        if isinstance((value := payload.get(key)), str) and value.strip()
    }
    query_code = request.query_params.get("warehouse_code")
    if query_code:
        warehouse_codes.add(query_code.strip().upper())
    path_code = request.path_params.get("warehouse_code")
    if path_code:
        warehouse_codes.add(str(path_code).strip().upper())
    if warehouse_codes:
        result.update(
            db.scalars(select(Warehouse.id).where(Warehouse.code.in_(warehouse_codes)))
        )
    logistic_unit_uid = payload.get("logistic_unit_uid") or payload.get("unit_uid")
    if isinstance(logistic_unit_uid, str):
        warehouse_id = _warehouse_id_for_unit(db, logistic_unit_uid)
        if warehouse_id is not None:
            result.add(warehouse_id)
    stock_position_id = payload.get("stock_position_id")
    if isinstance(stock_position_id, int):
        position = db.get(StockPosition, stock_position_id)
        warehouse_id = _warehouse_id_for_position(db, position) if position else None
        if warehouse_id is not None:
            result.add(warehouse_id)
    location_code = payload.get("location_code")
    if isinstance(location_code, str):
        location = db.scalar(select(Location).where(Location.code == location_code.upper()))
        if location:
            result.add(location.warehouse_id)

    segments = [segment for segment in request.url.path.split("/") if segment]
    if len(segments) < 3:
        return result
    root = segments[1] if segments[0] == "api" else ""
    object_uid = segments[2] if len(segments) > 2 else None
    if root == "logistic-units" and object_uid:
        warehouse_id = _warehouse_id_for_unit(db, object_uid)
        if warehouse_id is not None:
            result.add(warehouse_id)
    elif root == "logistic-shipments" and object_uid:
        item = db.scalar(
            select(LogisticShipment).where(LogisticShipment.shipment_uid == object_uid.upper())
        )
        if item:
            result.add(item.warehouse_id)
    elif root == "logistic-transfers" and object_uid:
        item = db.scalar(
            select(LogisticTransfer).where(LogisticTransfer.transfer_uid == object_uid.upper())
        )
        if item:
            result.update({item.source_warehouse_id, item.destination_warehouse_id})
    elif root == "logistic-inventories" and object_uid:
        item = db.scalar(
            select(LogisticInventory).where(LogisticInventory.inventory_uid == object_uid.upper())
        )
        if item:
            result.add(item.warehouse_id)
    elif root == "logistic-tasks" and object_uid:
        item = db.scalar(
            select(LogisticTask).where(LogisticTask.task_uid == object_uid.upper())
        )
        if item:
            result.add(item.warehouse_id)
    elif root == "locations" and object_uid:
        item = db.scalar(select(Location).where(Location.code == object_uid.upper()))
        if item:
            result.add(item.warehouse_id)
    elif root == "stock-reservations" and object_uid:
        item = db.scalar(select(StockReservation).where(StockReservation.uid == object_uid.upper()))
        if item and item.stock_position_id:
            position = db.get(StockPosition, item.stock_position_id)
            warehouse_id = _warehouse_id_for_position(db, position) if position else None
            if warehouse_id is not None:
                result.add(warehouse_id)
    elif root == "stock-reservation-requests" and object_uid:
        item = db.scalar(
            select(StockReservationRequest).where(
                StockReservationRequest.uid == object_uid.upper()
            )
        )
        if item and item.requested_logistic_unit_uid:
            warehouse_id = _warehouse_id_for_unit(db, item.requested_logistic_unit_uid)
            if warehouse_id is not None:
                result.add(warehouse_id)
    return result


async def authorize_api_request(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthenticationContext | None:
    if not settings.auth_enforcement_enabled:
        return None
    context = authentication_context(request, db, settings)
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return context
    if context.user.must_change_password:
        raise _forbidden("password change is required before warehouse operations")
    if context.user.role == UserRole.ADMIN:
        return context
    segments = [segment for segment in request.url.path.split("/") if segment]
    root = segments[1] if len(segments) > 1 and segments[0] == "api" else ""
    if root not in ROLE_MUTATION_ROOTS.get(context.user.role, set()):
        raise _forbidden("role does not permit this warehouse operation")
    warehouse_ids = await request_warehouse_ids(db, request)
    if warehouse_ids:
        allowed_ids = set(
            db.scalars(
                select(UserWarehouseAccess.warehouse_id).where(
                    UserWarehouseAccess.user_id == context.user.id
                )
            )
        )
        if not warehouse_ids.issubset(allowed_ids):
            raise _forbidden("operation references an unavailable warehouse")
    return context


def logout_session(
    db: Session,
    context: AuthenticationContext,
    request: Request,
) -> None:
    if context.session.revoked_at is None:
        context.session.revoked_at = utcnow()
        context.session.revoke_reason = "logout"
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.LOGOUT,
        succeeded=True,
        request=request,
        user=context.user,
        authentication_method=context.session.authentication_method,
        session_uid=context.session.uid,
    )
    db.commit()


def revoke_user_sessions(
    db: Session,
    user: User,
    *,
    reason: str,
    request: Request,
    actor: User,
) -> int:
    now = utcnow()
    sessions = list(
        db.scalars(
            select(AuthenticationSession)
            .where(
                AuthenticationSession.user_id == user.id,
                AuthenticationSession.revoked_at.is_(None),
            )
            .with_for_update()
        )
    )
    for session in sessions:
        session.revoked_at = now
        session.revoke_reason = reason
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.SESSIONS_REVOKED,
        succeeded=True,
        request=request,
        user=user,
        username=user.username,
        reason=f"{reason}; actor={actor.username}; count={len(sessions)}",
    )
    db.commit()
    return len(sessions)


def change_password(
    db: Session,
    user: User,
    payload: AuthenticationPasswordChangeRequest,
    request: Request,
) -> None:
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or not verify_password(payload.current_password, locked_user.password_hash):
        raise _unauthorized("current password is invalid")
    if hmac.compare_digest(payload.current_password, payload.new_password):
        raise _conflict("new password must differ from current password")
    locked_user.password_hash = hash_password(payload.new_password)
    locked_user.password_changed_at = utcnow()
    locked_user.must_change_password = False
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.PASSWORD_CHANGED,
        succeeded=True,
        request=request,
        user=locked_user,
    )
    db.commit()


def reset_user_password(
    db: Session,
    user: User,
    payload: AuthenticationAdminPasswordResetRequest,
    request: Request,
    actor: User,
) -> None:
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None:
        raise _conflict("user does not exist")
    locked_user.password_hash = hash_password(payload.new_password)
    locked_user.password_changed_at = utcnow()
    locked_user.must_change_password = payload.must_change_password
    locked_user.failed_login_count = 0
    locked_user.locked_until = None
    sessions = list(
        db.scalars(
            select(AuthenticationSession)
            .where(
                AuthenticationSession.user_id == user.id,
                AuthenticationSession.revoked_at.is_(None),
            )
            .with_for_update()
        )
    )
    now = utcnow()
    for session in sessions:
        session.revoked_at = now
        session.revoke_reason = "password_reset"
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.PASSWORD_CHANGED,
        succeeded=True,
        request=request,
        user=locked_user,
        reason=f"{payload.reason}; actor={actor.username}; sessions={len(sessions)}",
    )
    db.commit()


def _replace_user_warehouses(
    db: Session,
    user: User,
    payload: UserWarehouseAssignmentRequest,
    actor: User,
) -> None:
    warehouses = list(
        db.scalars(select(Warehouse).where(Warehouse.id.in_(payload.warehouse_ids)))
    ) if payload.warehouse_ids else []
    if len(warehouses) != len(payload.warehouse_ids):
        raise _conflict("one or more warehouses do not exist")
    existing = list(
        db.scalars(
            select(UserWarehouseAccess).where(UserWarehouseAccess.user_id == user.id)
        )
    )
    for access in existing:
        db.delete(access)
    for warehouse_id in payload.warehouse_ids:
        db.add(
            UserWarehouseAccess(
                user_id=user.id,
                warehouse_id=warehouse_id,
                is_default=warehouse_id == payload.default_warehouse_id,
                assigned_by_user_id=actor.id,
            )
        )


def create_authenticated_user(
    db: Session,
    payload: AuthenticationAdminUserCreate,
    actor: User,
) -> User:
    if db.scalar(select(User.id).where(User.username == payload.username)) is not None:
        raise _conflict("user already exists")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        password_changed_at=utcnow(),
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    db.flush()
    _replace_user_warehouses(
        db,
        user,
        UserWarehouseAssignmentRequest(
            warehouse_ids=payload.warehouse_ids,
            default_warehouse_id=payload.default_warehouse_id,
        ),
        actor,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("user conflicts with existing data") from exc
    db.refresh(user)
    return user


def assign_user_warehouses(
    db: Session,
    user: User,
    payload: UserWarehouseAssignmentRequest,
    actor: User,
) -> User:
    _replace_user_warehouses(db, user, payload, actor)
    db.commit()
    db.refresh(user)
    return user


def create_workstation(
    db: Session,
    payload: WarehouseWorkstationCreate,
) -> WarehouseWorkstation:
    if db.get(Warehouse, payload.warehouse_id) is None:
        raise _conflict("warehouse does not exist")
    workstation = WarehouseWorkstation(**payload.model_dump())
    db.add(workstation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("workstation already exists") from exc
    db.refresh(workstation)
    return workstation


def issue_access_pass(
    db: Session,
    *,
    user: User,
    payload: UserAccessPassIssueRequest,
    actor: User,
    request: Request,
    require_password: bool,
) -> tuple[UserAccessPass, str]:
    if require_password and user.must_change_password:
        raise _forbidden("password change is required before issuing an access pass")
    if require_password and not verify_password(payload.current_password or "", user.password_hash):
        raise _unauthorized("password confirmation failed")
    if actor.role != UserRole.ADMIN and actor.id != user.id:
        issuable_roles = {
            UserRole.PRODUCTION_OPERATOR,
            UserRole.RECEIVING_CLERK,
            UserRole.WAREHOUSE_CLERK,
            UserRole.SHIPPING_OPERATOR,
        }
        if user.role not in issuable_roles:
            raise _forbidden("senior role cannot issue a pass for a privileged user")
    workstation = db.scalar(
        select(WarehouseWorkstation)
        .where(WarehouseWorkstation.code == payload.workstation_code)
        .with_for_update()
    )
    if workstation is None or not workstation.is_active or not workstation.pass_login_enabled:
        raise _conflict("workstation does not allow access-pass login")
    if actor.role != UserRole.ADMIN:
        actor_warehouse_ids = set(
            db.scalars(
                select(UserWarehouseAccess.warehouse_id).where(
                    UserWarehouseAccess.user_id == actor.id
                )
            )
        )
        if workstation.warehouse_id not in actor_warehouse_ids:
            raise _forbidden("workstation belongs to an unavailable warehouse")
    user_warehouse_ids = set(
        db.scalars(
            select(UserWarehouseAccess.warehouse_id).where(
                UserWarehouseAccess.user_id == user.id
            )
        )
    )
    if user.role != UserRole.ADMIN and workstation.warehouse_id not in user_warehouse_ids:
        raise _forbidden("user has no access to the workstation warehouse")

    now = utcnow()
    active_passes = list(
        db.scalars(
            select(UserAccessPass)
            .where(
                UserAccessPass.user_id == user.id,
                UserAccessPass.revoked_at.is_(None),
            )
            .with_for_update()
        )
    )
    for active_pass in active_passes:
        active_pass.revoked_at = now
        active_pass.revoke_reason = "rotated"
    if active_passes:
        add_authentication_event(
            db,
            event_type=AuthenticationEventType.ACCESS_PASS_REVOKED,
            succeeded=True,
            request=request,
            user=user,
            authentication_method=AuthenticationMethod.ACCESS_PASS,
            workstation_code=workstation.code,
            reason=f"rotated; actor={actor.username}; count={len(active_passes)}",
        )
    raw_code = f"{ACCESS_PASS_PREFIX}.{secrets.token_urlsafe(32)}"
    access_pass = UserAccessPass(
        uid=f"PAS-{secrets.token_hex(10).upper()}",
        user_id=user.id,
        token_hash=token_hash(raw_code),
        workstation_id=workstation.id,
        issued_by_user_id=actor.id,
        issued_at=now,
        expires_at=(
            now + timedelta(days=payload.expires_days)
            if payload.expires_days is not None
            else None
        ),
    )
    db.add(access_pass)
    db.flush()
    add_authentication_event(
        db,
        event_type=AuthenticationEventType.ACCESS_PASS_ISSUED,
        succeeded=True,
        request=request,
        user=user,
        authentication_method=AuthenticationMethod.ACCESS_PASS,
        workstation_code=workstation.code,
        reason=f"{payload.reason}; actor={actor.username}; revoked={len(active_passes)}",
    )
    db.commit()
    db.refresh(access_pass)
    return access_pass, raw_code


def access_pass_payload(db: Session, access_pass: UserAccessPass) -> dict:
    user = db.get(User, access_pass.user_id)
    workstation = db.get(WarehouseWorkstation, access_pass.workstation_id)
    return {
        "uid": access_pass.uid,
        "user_id": access_pass.user_id,
        "username": user.username if user else "",
        "workstation_id": access_pass.workstation_id,
        "workstation_code": workstation.code if workstation else "",
        "issued_by_user_id": access_pass.issued_by_user_id,
        "issued_at": access_pass.issued_at,
        "expires_at": access_pass.expires_at,
        "last_used_at": access_pass.last_used_at,
        "revoked_at": access_pass.revoked_at,
    }


def workstation_payload(db: Session, workstation: WarehouseWorkstation) -> dict:
    warehouse = db.get(Warehouse, workstation.warehouse_id)
    return {
        "id": workstation.id,
        "code": workstation.code,
        "name": workstation.name,
        "warehouse_id": workstation.warehouse_id,
        "warehouse_code": warehouse.code if warehouse else "",
        "pass_login_enabled": workstation.pass_login_enabled,
        "is_active": workstation.is_active,
        "created_at": workstation.created_at,
    }
