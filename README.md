# IrsBot

本地部署的 AI Agent 应用（单用户）。浏览器里对话，网页端填自己的 LLM API Key，具备 Skill / Tool / MCP / RAG 能力。**不接 IM、不做独立网页版**。

一条命令启动，唯一前置条件是**装一次 Docker**。

---

## 1. 前置条件

- 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Windows / macOS）并启动。
- Windows 用户用 **PowerShell** 或文件管理器操作；脚本为 `scripts/*.cmd`。
- macOS / Linux 用户用终端，脚本为 `scripts/*.sh`（需 `chmod +x scripts/*.sh`）。

---

## 2. 一键启动（5 分钟跑通）

### Windows

```powershell
# 进入项目根目录，双击或运行：
scripts\start.cmd
```

### macOS / Linux

```bash
chmod +x scripts/*.sh
./scripts/start.sh
```

脚本会自动完成：

1. 若没有 `.env`，从 `.env.example` 复制生成（不覆盖已有）。
2. **首次引导**：若 `SECRET_KEY` / 管理员密码还是模板默认值 `changethis`，随机生成强密码并写回 `.env`（你已有的真实 `SECRET_KEY` 不会被覆盖）。
3. 检查 Docker 是否在运行。
4. `docker compose up -d --build` 拉起 `db` / `milvus` / `backend`。
5. 轮询健康检查，最多等 3 分钟。
6. 打印访问地址 + 管理员账号 + **密码**，并自动打开浏览器。

> 🔑 **管理员密码只在终端打印一次**。窗口会停在 `Press any key to close…`，
> 看完再关。若关太快没看见，直接打开项目根目录的 `.env`，看
> `FIRST_SUPERUSER_PASSWORD=` 一行即可（已落盘）。
> 默认管理员账号：`admin@example.com`。

启动成功后访问：**http://localhost:8000**

---

## 3. 干净重来（删掉所有数据，从零构建）

> ⚠️ 这会**删除**数据库与向量库里的全部会话、知识库、配置。只在你想从绝对干净的状态重新开始时用。

```powershell
scripts\reset.cmd        # Windows
./scripts/reset.sh       # macOS / Linux
```

它等价于 `docker compose down -v` + 重新 `start`。

---

## 4. 停止

```powershell
scripts\stop.cmd         # Windows
./scripts/stop.sh        # macOS / Linux
```

默认 `docker compose down` **保留数据卷**（下次启动数据还在）。
要彻底清空数据再加 `-v`：`docker compose down -v`。

---

## 5. 常见排查

| 现象 | 处理 |
|---|---|
| 提示 `Docker not available` | 先启动 Docker Desktop |
| 浏览器弹出但 cmd 窗口消失 | 正常（双击 .cmd 会自动关窗），密码在 `.env` 里；建议右键「以管理员身份运行」或在终端里 `cd` 进去跑 `scripts\start.cmd` |
| 3 分钟还没 ready | `docker compose logs -f backend` 看后端报错 |
| 改了前端代码要生效 | 在仓库根 `bun run --filter frontend build` 重新构建 `frontend/dist`；后端已绑定挂载 `./frontend/dist`，刷新即可（无需重建镜像） |
| 登录失败 | 确认用的是 `.env` 里的 `FIRST_SUPERUSER_PASSWORD`，不是 `changethis` |

服务状态自检：

```powershell
docker compose ps                       # 三个服务都应是 healthy / Up
curl.exe -s http://localhost:8000/api/v1/utils/health-check/   # 期望返回 true
```

---

## 6. 分发给别人（可移植性）

前端产物使用**相对路径 `/api`**，构建时**不烤死任何 host/port**。因此：

- 把整个仓库拷给另一台装了 Docker 的机器；
- 对方直接跑 `scripts/start.cmd`（或 `.sh`）；
- 在 `localhost:8000` 或任意自定义域名/端口都能用，**无需重新构建前端**。

前提：对方机器上 `frontend/dist` 已存在（你提交仓库时带上它，或对方先 `bun run --filter frontend build`）。

---

## 7. 测试基线

需要本机有可连的 PostgreSQL（或容器起来后用容器内 PG）。在 `backend/` 目录：

```bash
# 294 个单元测试
uv run pytest -q
# 18 个集成测试（注意：不带 -m integration 会被默认跳过）
uv run pytest -m integration -q
```

⚠️ 测试安全闸：`tests/conftest.py` 会拒绝在真实库（`POSTGRES_DB` 不是 `test_app`）上运行，
防止误清空数据。需要连真实库调试时显式设 `IRSBOT_ALLOW_NONTEST_DB=1`。

---

## 8. 相关文档

- 后端开发：`backend/README.md`
- 前端开发：`frontend/README.md`
- 运维（备份 / 恢复 / 卸载）：`docs/OPERATIONS.md`
- 架构与施工计划：`plan/`（含 `progress.md`、`local-deployment-plan.md`）

## 技术栈

- 后端：FastAPI + SQLModel + PostgreSQL + Milvus（向量）+ LangGraph
- 前端：React + TypeScript + Vite + Tailwind + shadcn/ui
- 部署：Docker Compose（单主机，一条命令启动）
