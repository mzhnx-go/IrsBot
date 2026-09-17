"""prestart 第三步：写入初始数据（superuser + 默认「模型源」）。

🔴 关键（2026-09-17 踩坑）：**默认模型源的播种逻辑在 `app.core.db.engine.init_db` 里** ——
它用 `settings.OPENAI_API_KEY / OPENAI_BASE_URL / DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL`
（见 `.env`）创建一条 `name="default"` 的 `ProviderConfig`（is_default / is_active 均为 True）。

本文件被前人误删后补的「精简版」**只建 superuser、没调 init_db** →
新库起来后「设置 → 模型源」页面是空的。
（现象看起来像"数据库被重置"，其实是**播种步骤压根没跑**。）

现改为**直接复用 init_db**，不再维护第二份逻辑，避免两边漂移。
init_db 自身幂等：superuser 按 email 判断、provider 按 name="default" 判断，已存在则跳过。

⚠️ 另有一个同名文件 `backend/app/scripts/init_data.py`（更早的版本，同样只调 init_db）。
prestart.sh 用的是**本文件**（`python scripts/init_data.py`），别改错地方。
"""

import logging

from sqlmodel import Session

from app.core.db.engine import engine, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    with Session(engine) as session:
        init_db(session)

    logger.info("initial data ready: superuser + default provider (if absent)")


if __name__ == "__main__":
    main()
