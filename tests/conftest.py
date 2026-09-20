import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

# 测试使用独立数据库/向量集合/知识库文件目录，避免污染开发、生产环境数据。
# 环境变量优先级高于 .env 文件（pydantic-settings），必须在导入 app 之前设置。
os.environ.setdefault("POSTGRES_DB", "test_app")
os.environ.setdefault("MILVUS_COLLECTION_PREFIX", "irsbot_kb_test")
os.environ.setdefault("KB_FILE_STORAGE_DIR", "./uploads/kb_test")

from app.core.config import settings  # noqa: E402

# 🔴 安全阀（2026-09-17 事故后加）：session 结束时本文件会 delete 掉**所有表的所有行**。
# 一旦 setdefault 没生效（比如终端/工具已把 .env 的 POSTGRES_DB=app 注入了进程环境），
# 测试就会连到**真实库**并在收尾阶段把它清空 —— 2026-09-17 00:55:57 就是这样把本机
# app 库（user / knowledge_bases 等 12 张表）清掉的。
# 所以这里**硬校验**一次，连的不是 test_app 就直接中止，绝不带病运行。
# 确有特殊需要（例如临时对某个库跑一次），显式设 IRSBOT_ALLOW_NONTEST_DB=1 放行。
if os.getenv("IRSBOT_ALLOW_NONTEST_DB") != "1":
    from sqlalchemy.engine import make_url as _make_url

    _db = _make_url(str(settings.SQLALCHEMY_DATABASE_URI)).database
    if _db != "test_app":
        raise RuntimeError(
            f"拒绝运行测试：当前数据库是 {_db!r}，不是 test_app。"
            "测试收尾会清空所有表，继续跑会毁掉真实数据。"
            "请检查环境变量 POSTGRES_DB（很可能被 .env / 终端注入成了 app）；"
            "确需指定其他库请显式设置 IRSBOT_ALLOW_NONTEST_DB=1。"
        )

from app.core.db.engine import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from tests.utils.user import authentication_token_from_email  # noqa: E402
from tests.utils.utils import get_superuser_token_headers  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def _ensure_test_db() -> None:
    """若测试库不存在，则自动创建（仅针对 test_app，避免影响其他环境）。"""
    url = make_url(str(settings.SQLALCHEMY_DATABASE_URI))
    if url.database != "test_app":
        return
    maintenance_url = url.set(database="postgres")
    # 必须传 URL 对象（str() 会把密码渲染成 *** 导致认证失败），且 CREATE DATABASE 需 AUTOCOMMIT
    with create_engine(maintenance_url, isolation_level="AUTOCOMMIT").connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'test_app'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE test_app"))


_ensure_test_db()


def _create_tables() -> None:
    """在测试库上创建全部表（开发/生产通过 Alembic 迁移建表，测试库直接按元数据建表）。"""
    from sqlmodel import SQLModel

    import app.core.db.models  # noqa: F401  # 确保业务表模型注册进 SQLModel.metadata

    SQLModel.metadata.create_all(engine)


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        _create_tables()
        init_db(session)
        yield session
        # 按外键依赖顺序清空（子表在前、父表在后），保证每次测试可重复运行
        from app.core.db.models import (  # noqa: F401
            AgentRun,
            AppSetting,
            Conversation,
            Document,
            KnowledgeBase,
            MCPServer,
            Message,
            Persona,
            ProviderConfig,
            Skill,
        )

        for model in [
            Message,
            AgentRun,
            Conversation,
            Document,
            KnowledgeBase,
            MCPServer,
            Persona,
            ProviderConfig,
            Skill,
            User,
            # ⚠️ 必清：运行时配置是全库共享的（无 user_id），一旦某条测试把
            # users.open_registration 写成 true，后续所有测试的注册闸门断言
            # 都会连带失效。
            AppSetting,
        ]:
            session.execute(delete(model))
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    """每个用例开始前清空限流窗口。

    限流 Stage 是进程级共享单例，窗口按 time.monotonic() 累计：整个测试会话里
    同一用户累计发言超过 RATE_LIMIT_REQUESTS（默认 20）就会开始拦截，
    于是测试结果取决于「跑得多快」——套件全量跑必红，单文件跑才绿。
    这不是被测行为（限流本身的测试各自构造实例或临时改 max_requests），
    所以这里按用例复位，让结果只反映代码而不是墙钟。
    """
    from app.core.pipeline.stages.rate_limit import get_rate_limit_stage

    get_rate_limit_stage()._requests.clear()


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
