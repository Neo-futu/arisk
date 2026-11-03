from sqlalchemy import event, text
from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.core.db_auth import generate_iam_token
from app.models import User, UserCreate

# 本地：静态密码 + localhost（默认）。云上：POSTGRES_IAM_AUTH=true 时，
# 每次新建连接注入新鲜的 RDS IAM token 作口令（token 约 15 分钟过期），
# 并强制 SSL。POSTGRES_SSLMODE 未显式设置且开启 IAM 时默认 require。
_connect_args: dict[str, str] = {}
if settings.POSTGRES_SSLMODE:
    _connect_args["sslmode"] = settings.POSTGRES_SSLMODE
elif settings.POSTGRES_IAM_AUTH:
    _connect_args["sslmode"] = "require"

engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    connect_args=_connect_args,
)

if settings.POSTGRES_IAM_AUTH:

    @event.listens_for(engine, "do_connect")
    def _provide_iam_token(dialect, conn_rec, cargs, cparams):  # type: ignore[no-untyped-def]
        cparams["password"] = generate_iam_token(
            host=settings.POSTGRES_SERVER,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            region=settings.AWS_REGION,
        )


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


# Local/demo accounts kept short for the Admin UI (email + display name).
_DEMO_USERS: tuple[tuple[str, str, str, bool], ...] = (
    # email, full_name, role_code, is_superuser
    ("risk@fsi.com", "Risk", "INVESTMENT_MANAGER", False),
    ("mgr@fsi.com", "Mgr", "INVESTMENT_DIRECTOR", False),
    ("view@fsi.com", "View", "PORTFOLIO_VIEWER", False),
)


def _ensure_role(session: Session, user_id, role_code: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO iam.user_role (user_id, role_id, created_at)
            SELECT :user_id, r.id, NOW()
            FROM iam.role r
            WHERE r.code = :role_code
            ON CONFLICT DO NOTHING
            """
        ),
        {"user_id": user_id, "role_code": role_code},
    )


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
            full_name="Admin",
        )
        user = crud.create_user(session=session, user_create=user_in)
    elif not user.full_name:
        user.full_name = "Admin"
        session.add(user)
        session.commit()
        session.refresh(user)

    # Ensure the bootstrap superuser holds SYSTEM_ADMIN so a fresh install (where the
    # superuser is created after the RBAC seed migration) still lands in a usable state.
    # Guarded so it is a no-op until the RBAC seed migration has run.
    try:
        _ensure_role(session, user.id, "SYSTEM_ADMIN")
        session.commit()
    except Exception:
        session.rollback()

    # Small set of short demo accounts for Admin / access demos (idempotent).
    try:
        for email, full_name, role_code, is_superuser in _DEMO_USERS:
            existing = session.exec(select(User).where(User.email == email)).first()
            if existing:
                if not existing.full_name:
                    existing.full_name = full_name
                    session.add(existing)
                    session.commit()
                _ensure_role(session, existing.id, role_code)
                session.commit()
                continue
            created = crud.create_user(
                session=session,
                user_create=UserCreate(
                    email=email,
                    password=settings.FIRST_SUPERUSER_PASSWORD,
                    full_name=full_name,
                    is_superuser=is_superuser,
                    is_active=True,
                ),
            )
            _ensure_role(session, created.id, role_code)
            session.commit()
    except Exception:
        session.rollback()
