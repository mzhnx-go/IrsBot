# 等待数据库就绪（prestart 第一步）。
# 模板原版在此文件里做"重试连接 PG"；项目改造时被误删但 prestart.sh 仍引用它。
# 精简重写：只做"等 db 可连"，不做别的。
import logging
import os
import time

from sqlalchemy import Engine, create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TRIES = 60
WAIT_SECONDS = 1


def get_engine() -> Engine:
    server = os.environ["POSTGRES_SERVER"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    return create_engine(
        f"postgresql+psycopg://{user}:{password}@{server}:{port}/{db}"
    )


def main() -> None:
    engine = get_engine()
    tries = 0
    while True:
        tries += 1
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception as e:  # noqa: BLE001
            logger.info(f"db not ready yet ({e})")
            if tries > MAX_TRIES:
                raise SystemExit(f"db not reachable after {MAX_TRIES} tries")
            time.sleep(WAIT_SECONDS)
    logger.info("db ready")


if __name__ == "__main__":
    main()
