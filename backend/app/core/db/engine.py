from sqlmodel import Session, create_engine, select

from app.core import crud
from app.core.config import settings
from app.core.db.models import ProviderConfig
from app.core.db.sqlmodel_models import User, UserCreate
from app.utils.crypto import encrypt_api_key

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.core.db.sqlmodel_models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
    else:
        # Keep .env as the source of truth for the superuser password.
        # This makes the "first-run random password" (D3.2) actually work:
        # the host bootstrap writes a random FIRST_SUPERUSER_PASSWORD into
        # .env, and we (re)apply it here so the printed password always logs
        # in, even if the superuser was created in an earlier run with the
        # old "changethis" default. No-op when the hash already matches.
        from app.core.auth.security import get_password_hash, verify_password

        verified, _ = verify_password(
            settings.FIRST_SUPERUSER_PASSWORD, user.hashed_password
        )
        if not verified:
            user.hashed_password = get_password_hash(settings.FIRST_SUPERUSER_PASSWORD)
            session.add(user)
            session.commit()
            session.refresh(user)

    provider = session.exec(
        select(ProviderConfig).where(ProviderConfig.name == "default")
    ).one_or_none()

    if not provider and user:
        provider = ProviderConfig(
            user_id=user.id,
            name="default",
            provider_type=settings.DEFAULT_LLM_PROVIDER,
            api_key=encrypt_api_key(settings.OPENAI_API_KEY),
            base_url=settings.OPENAI_BASE_URL,
            model_name=settings.DEFAULT_LLM_MODEL,
            is_default=True,
            is_active=True,
        )
        session.add(provider)
        session.commit()
