from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    AuthenticationContext,
    access_pass_payload,
    assign_user_warehouses,
    authenticate_with_access_pass,
    authenticate_with_password,
    bootstrap_administrator,
    change_password,
    create_authenticated_user,
    create_workstation,
    issue_access_pass,
    logout_session,
    require_administrator,
    require_authentication_context,
    require_pass_issuer,
    require_security_reader,
    reset_user_password,
    revoke_user_sessions,
    user_payload,
    update_authenticated_user,
    update_workstation,
    workstation_payload,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.entities import (
    AuthenticationEvent,
    User,
    UserAccessPass,
    UserWarehouseAccess,
    WarehouseWorkstation,
)
from app.models.enums import UserRole
from app.schemas import (
    AuthenticationAdminPasswordResetRequest,
    AuthenticationAdminUserCreate,
    AuthenticationAdminUserUpdate,
    AuthenticationBootstrapRequest,
    AuthenticationEventRead,
    AuthenticationPassLoginRequest,
    AuthenticationPasswordChangeRequest,
    AuthenticationPasswordLoginRequest,
    AuthenticationResult,
    AuthenticationRevokeSessionsRequest,
    AuthenticationUserRead,
    UserAccessPassIssueRead,
    UserAccessPassIssueRequest,
    UserAccessPassRead,
    UserWarehouseAssignmentRequest,
    WarehouseWorkstationCreate,
    WarehouseWorkstationRead,
    WarehouseWorkstationUpdate,
)


router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _set_session_cookie(
    response: Response,
    raw_token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=raw_token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _authentication_result(
    db: Session,
    *,
    user: User,
    session,
    raw_token: str,
    workstation,
) -> dict:
    return {
        "session_uid": session.uid,
        "session_token": raw_token,
        "authentication_method": session.authentication_method,
        "workstation_code": workstation.code if workstation else None,
        "expires_at": session.expires_at,
        "user": user_payload(db, user),
    }


@router.post("/bootstrap", response_model=AuthenticationUserRead)
def api_bootstrap_administrator(
    payload: AuthenticationBootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user = bootstrap_administrator(db, payload, request, settings)
    return user_payload(db, user)


@router.post("/login/password", response_model=AuthenticationResult)
def api_login_with_password(
    payload: AuthenticationPasswordLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user, session, raw_token, workstation = authenticate_with_password(
        db,
        payload,
        request,
        settings,
    )
    _set_session_cookie(response, raw_token, settings)
    return _authentication_result(
        db,
        user=user,
        session=session,
        raw_token=raw_token,
        workstation=workstation,
    )


@router.post("/login/pass", response_model=AuthenticationResult)
def api_login_with_access_pass(
    payload: AuthenticationPassLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user, session, raw_token, workstation = authenticate_with_access_pass(
        db,
        payload,
        request,
        settings,
    )
    _set_session_cookie(response, raw_token, settings)
    return _authentication_result(
        db,
        user=user,
        session=session,
        raw_token=raw_token,
        workstation=workstation,
    )


@router.get("/me", response_model=AuthenticationUserRead)
def api_current_user(
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
) -> dict:
    return user_payload(db, context.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def api_logout(
    request: Request,
    response: Response,
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    logout_session(db, context, request)
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
def api_change_password(
    payload: AuthenticationPasswordChangeRequest,
    request: Request,
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
) -> Response:
    change_password(db, context.user, payload, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
def api_revoke_own_sessions(
    payload: AuthenticationRevokeSessionsRequest,
    request: Request,
    response: Response,
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    revoke_user_sessions(
        db,
        context.user,
        reason=payload.reason,
        request=request,
        actor=context.user,
    )
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/passes/issue", response_model=UserAccessPassIssueRead)
def api_issue_own_access_pass(
    payload: UserAccessPassIssueRequest,
    request: Request,
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
) -> dict:
    access_pass, raw_code = issue_access_pass(
        db,
        user=context.user,
        payload=payload,
        actor=context.user,
        request=request,
        require_password=True,
    )
    result = access_pass_payload(db, access_pass)
    return {
        **result,
        "login_code": raw_code,
        "qr_payload": raw_code,
        "code128_payload": raw_code,
    }


@router.get("/passes", response_model=list[UserAccessPassRead])
def api_list_own_access_passes(
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    passes = db.scalars(
        select(UserAccessPass)
        .where(UserAccessPass.user_id == context.user.id)
        .order_by(UserAccessPass.issued_at.desc())
    )
    return [access_pass_payload(db, item) for item in passes]


@router.get("/workstations", response_model=list[WarehouseWorkstationRead])
def api_list_available_workstations(
    context: AuthenticationContext = Depends(require_authentication_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(WarehouseWorkstation).where(
        WarehouseWorkstation.is_active.is_(True),
        WarehouseWorkstation.pass_login_enabled.is_(True),
    )
    if context.user.role != UserRole.ADMIN:
        warehouse_ids = select(UserWarehouseAccess.warehouse_id).where(
            UserWarehouseAccess.user_id == context.user.id
        )
        query = query.where(WarehouseWorkstation.warehouse_id.in_(warehouse_ids))
    workstations = db.scalars(query.order_by(WarehouseWorkstation.code))
    return [workstation_payload(db, workstation) for workstation in workstations]


@router.post("/admin/users", response_model=AuthenticationUserRead)
def api_create_authenticated_user(
    payload: AuthenticationAdminUserCreate,
    context: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    user = create_authenticated_user(db, payload, context.user)
    return user_payload(db, user)


@router.get("/admin/users", response_model=list[AuthenticationUserRead])
def api_list_authenticated_users(
    _: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> list[dict]:
    users = db.scalars(select(User).order_by(User.username))
    return [user_payload(db, user) for user in users]


@router.put("/admin/users/{user_id}", response_model=AuthenticationUserRead)
def api_update_authenticated_user(
    user_id: int,
    payload: AuthenticationAdminUserUpdate,
    request: Request,
    context: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    updated = update_authenticated_user(db, user, payload, context.user, request)
    return user_payload(db, updated)


@router.put(
    "/admin/users/{user_id}/warehouses",
    response_model=AuthenticationUserRead,
)
def api_assign_user_warehouses(
    user_id: int,
    payload: UserWarehouseAssignmentRequest,
    context: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    assign_user_warehouses(db, user, payload, context.user)
    return user_payload(db, user)


@router.post(
    "/admin/users/{user_id}/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_reset_user_password(
    user_id: int,
    payload: AuthenticationAdminPasswordResetRequest,
    request: Request,
    context: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    reset_user_password(db, user, payload, request, context.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/users/{user_id}/passes/issue",
    response_model=UserAccessPassIssueRead,
)
def api_issue_user_access_pass(
    user_id: int,
    payload: UserAccessPassIssueRequest,
    request: Request,
    context: AuthenticationContext = Depends(require_pass_issuer),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    access_pass, raw_code = issue_access_pass(
        db,
        user=user,
        payload=payload,
        actor=context.user,
        request=request,
        require_password=False,
    )
    result = access_pass_payload(db, access_pass)
    return {
        **result,
        "login_code": raw_code,
        "qr_payload": raw_code,
        "code128_payload": raw_code,
    }


@router.post(
    "/admin/workstations",
    response_model=WarehouseWorkstationRead,
)
def api_create_workstation(
    payload: WarehouseWorkstationCreate,
    _: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    return workstation_payload(db, create_workstation(db, payload))


@router.get(
    "/admin/workstations",
    response_model=list[WarehouseWorkstationRead],
)
def api_list_workstations(
    _: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> list[dict]:
    workstations = db.scalars(select(WarehouseWorkstation).order_by(WarehouseWorkstation.code))
    return [workstation_payload(db, workstation) for workstation in workstations]


@router.put(
    "/admin/workstations/{workstation_id}",
    response_model=WarehouseWorkstationRead,
)
def api_update_workstation(
    workstation_id: int,
    payload: WarehouseWorkstationUpdate,
    request: Request,
    context: AuthenticationContext = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    workstation = db.get(WarehouseWorkstation, workstation_id)
    if workstation is None:
        raise HTTPException(status_code=404, detail="workstation not found")
    updated = update_workstation(db, workstation, payload, context.user, request)
    return workstation_payload(db, updated)


@router.get("/admin/events", response_model=list[AuthenticationEventRead])
def api_list_authentication_events(
    succeeded: bool | None = Query(default=None),
    username: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthenticationContext = Depends(require_security_reader),
    db: Session = Depends(get_db),
) -> list[AuthenticationEvent]:
    query = select(AuthenticationEvent)
    if succeeded is not None:
        query = query.where(AuthenticationEvent.succeeded == succeeded)
    if username is not None:
        query = query.where(AuthenticationEvent.username == username.strip().lower())
    return list(
        db.scalars(
            query.order_by(AuthenticationEvent.created_at.desc()).limit(limit)
        )
    )
