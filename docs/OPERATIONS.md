# IrsBot 运维手册：备份 / 恢复 / 卸载

> 适用对象：本地单用户部署（`docker compose` 一键启动）。
> 本文聚焦「数据在哪、怎么备份、怎么恢复、怎么卸载」，与 `README.md`（5 分钟跑通）互补。
> 所有命令默认在项目根目录 `d:\AIpy\full-stack\IrsBot` 执行。

---

## 0. 数据资产清单（先看懂这个，恢复/卸载才不慌）

| 资产 | 存哪 | 形态 | `docker compose down` 是否保留 | `down -v` / `reset.cmd` 是否清除 |
|---|---|---|---|---|
| 业务数据库（用户 / 模型源 / 会话 / 消息 / KB 元数据） | 命名卷 `irsbot_app-db-data` → 容器内 `/var/lib/postgresql/data/pgdata` | Docker 命名卷 | ✅ 保留 | ❌ **被删除** |
| 向量库（RAG 嵌入向量 + 索引） | **绑定挂载** `D:/Milvus/volumes/milvus` → 容器 `/var/lib/milvus` | 宿主机目录 | ✅ 保留 | ✅ **保留**（`-v` 只删命名卷，删不到宿主目录） |
| 知识库原始文档 / 附件 | `backend/uploads/`（开发模式由 override 同步进容器） | 宿主机目录 | ✅ 保留 | ✅ **保留**（同上是宿主目录） |
| 密钥与配置（`.env`） | 项目根 `.env` | 宿主机文件 | ✅ 保留 | ✅ **保留** |
| 前端产物 | `frontend/dist/`（绑定挂载进 backend 容器） | 宿主机目录 | ✅ 保留 | ✅ **保留** |

> ⚠️ **关键认知**：本项目只有 PostgreSQL 是「Docker 命名卷」，`docker compose down -v` 只会清它。
> Milvus 向量、uploads、`.env`、dist 全是**宿主机目录/文件**，`-v` 删不到它们。
> → 这就是为什么「干净重来」（`reset.cmd`）会清空数据库、却**留下旧向量**——见第 3 节陷阱。

---

## 1. 备份（Backup）

### 一键备份

```powershell
scripts\backup.cmd          # Windows（双击或 PowerShell 运行）
# 或：
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
```

脚本是**只读**的：只读取、拷贝、归档，**绝不删除任何数据**。

### 它捕获了什么

落盘到 `backups/<yyyyMMdd_HHmmss>/`，并生成 `MANIFEST.txt` 清单：

| 文件 | 内容 | 是否含密钥 |
|---|---|---|
| `irsbot_app_container_<ts>.dump` | 容器内 `app` 库 `pg_dump -Fc`（自定义格式，可恢复） | 含用户密码**哈希**（非明文） |
| `irsbot_app_local_<ts>.dump` | 本机 PostgreSQL `app` 库 dump（若可达；否则跳过并记入清单） | 同上 |
| `env_backup_<ts>.env` | `.env` 完整副本 | ⚠️ **含明文** SECRET_KEY / API Key / DB 密码 / 管理员密码 |
| `uploads/` | 知识库原始文档 + 附件（`backend/uploads` 的副本） | 否 |
| `irsbot_app-db-data_<ts>.tar.gz` | 命名卷 tar（有 busybox/alpine 镜像时生成；否则跳过并记入清单） | 否 |
| `milvus_data_host_<...>/`（目录副本） | `D:/Milvus/volumes/milvus` 完整拷贝（etcd 锁文件由 robocopy 拷出） | 否 |

> 备份前会确保 `backups/` 已加入 `.gitignore`（含密钥，禁止提交到仓库）。

### 注意事项

- ⚠️ **备份含密钥**：`env_backup_*.env` 是明文敏感文件，妥善存放，不要传到 git / 网盘。
- 备份**不暂停服务**：`pg_dump` 对运行中的库做一致性快照，无需停机。
- 备份只跑一次就够；定期可重复执行，每次生成独立时间戳目录。

---

## 2. 恢复（Restore）

> 恢复前先 `docker compose down` 停掉相关服务，避免写入冲突。恢复完再 `start`。

### 2.1 仅恢复数据库（PostgreSQL）

场景：库被误操作清空 / 想回滚到某次备份的库内容（向量和文档仍在）。

```powershell
cd d:\AIpy\full-stack\IrsBot
# 0) 停服务（保留 milvus / uploads，不动它们）
docker compose down backend prestart

# 1) 把 dump 拷进 db 容器
docker cp "backups\<ts>\irsbot_app_container_<ts>.dump" irsbot-db-1:/tmp/restore.dump

# 2) 恢复（--clean --if-exists 先清后建；目标库 app 必须已存在，prestart 会建好）
#    密码取自已备份的 .env（env_backup_*.env 第一行 POSTGRES_PASSWORD=...）
$env:PGPASSWORD = "<你的POSTGRES_PASSWORD>"
docker exec -e PGPASSWORD=$env:PGPASSWORD irsbot-db-1 `
  pg_restore -U postgres -d app -Fc --clean --if-exists /tmp/restore.dump

# 3) 重新拉起
docker compose up -d
```

> 验证：`docker compose exec db psql -U postgres -d app -c "SELECT count(*) FROM \"user\";"` 应 > 0。

### 2.2 仅恢复向量库（Milvus）

场景：向量目录损坏 / 误删集合，想用备份的向量恢复（库元数据仍在）。

```powershell
cd d:\AIpy\full-stack\IrsBot
# 1) 停 milvus（etcd 锁文件必须释放才能安全替换）
docker compose stop milvus

# 2) 用备份目录覆盖宿主数据目录
#    若备份是目录副本（milvus_data_host_<...>/）：
robocopy "backups\<ts>\milvus_data_host_<...>" "D:\Milvus\volumes\milvus" /E /R:0 /W:0 /NFL /NDL /XJ
#    若备份是 tar.gz（irsbot_app-db-data_<ts>.tar.gz 同机制生成的 milvus 卷）：
#    docker run --rm -v ${PWD}/backups/<ts>:/b -v D:/Milvus/volumes/milvus:/v busybox `
#      tar xzf /b/<milvus卷>.tar.gz -C /v

# 3) 重新拉起
docker compose up -d milvus
```

> ⚠️ 替换前务必先 `docker compose stop milvus`，否则 etcd 锁文件被占用、拷贝不完整。

### 2.3 全盘恢复（库 + 向量 + 文档 + 配置）

完整回滚到某次备份点：

```powershell
cd d:\AIpy\full-stack\IrsBot
docker compose down

# 数据库
docker compose up -d db
docker cp "backups\<ts>\irsbot_app_container_<ts>.dump" irsbot-db-1:/tmp/restore.dump
$env:PGPASSWORD = "<你的POSTGRES_PASSWORD>"
docker exec -e PGPASSWORD=$env:PGPASSWORD irsbot-db-1 `
  pg_restore -U postgres -d app -Fc --clean --if-exists /tmp/restore.dump

# 向量库
docker compose stop milvus
robocopy "backups\<ts>\milvus_data_host_<...>" "D:\Milvus\volumes\milvus" /E /R:0 /W:0 /NFL /NDL /XJ

# 知识库原始文档
robocopy "backups\<ts>\uploads" "backend\uploads" /E /R:0 /W:0 /NFL /NDL /XJ

# 配置（仅当你要还原当时的密钥；否则保留当前 .env）
copy /y "backups\<ts>\env_backup_<ts>.env" ".env"

# 重新拉起全部
docker compose up -d
```

> 🔑 **一致性要点**：库、向量、uploads 三者必须来自**同一次备份**，否则会出现
> 「向量指向不存在的 KB」或「KB 记录找不到原始文档」的不一致。

---

## 3. 卸载（Uninstall）

### 3.1 停服务但保留数据（最常用）

```powershell
scripts\stop.cmd          # 等价于 docker compose down
# 或
docker compose down
```

数据库卷、Milvus 目录、uploads、`.env` 全部保留，下次 `start` 数据还在。

### 3.2 干净重来（清空数据库，从零开始）

```powershell
scripts\reset.cmd         # = docker compose down -v + start
```

⚠️ 这会**删除命名卷 `irsbot_app-db-data`**（清空所有会话 / 知识库 / 配置）。
但如第 0 节所述，**Milvus 向量目录、uploads、`.env` 不会被删**。

> 🔴 **陷阱（务必知道）**：`reset.cmd` / `down -v` 只清 PG，**不碰 Milvus 绑定挂载**。
> 结果：重启后 PG 是空的，但 Milvus 里还留着旧集合 → RAG 检索会返回指向已删除 KB 的向量，行为异常。
>
> **修复**：若想真正「全清」，在 `reset.cmd` 前额外删掉向量目录：
> ```powershell
> docker compose stop milvus
> Remove-Item -Recurse -Force "D:\Milvus\volumes\milvus"
> scripts\reset.cmd
> ```
> （uploads 同理，需要的话一并删 `backend/uploads`）

### 3.3 彻底卸载（连 Docker 镜像/容器/宿主数据一起清）

适合「这机器不再用 IrsBot 了」：

```powershell
cd d:\AIpy\full-stack\IrsBot

# 1) 停并删容器 + 命名卷
docker compose down -v

# 2) 删宿主数据（这些 -v 删不到）
Remove-Item -Recurse -Force "D:\Milvus\volumes\milvus"     # Milvus 向量
Remove-Item -Recurse -Force "backend\uploads"             # 知识库原始文档（可选）

# 3) 删配置与镜像产物（按需要）
#    .env 含密钥，若确定不再用可删；想保留密码就留着
Remove-Item -Force ".env"
docker image rm irsbot-backend irsbot-prestart           # 本地构建的镜像
docker image rm milvusdb/milvus:v2.6.14                  # 若不再需要可删（下次 start 会重新拉）

# 4) 清理旧版回滚容器（Phase D1 改名保留的那个）
docker rm -f milvus-standalone-old 2>$null

# 5) 备份目录（你自己的，默认保留；确认无用再删）
#    Remove-Item -Recurse -Force "backups"
```

> 卸载后 `docker system prune -a` 可进一步回收悬空镜像/网络（会删所有未用镜像，慎用）。

---

## 4. 常见排查

| 现象 | 处理 |
|---|---|
| `pg_restore` 报 `role "postgres" does not exist` | 容器内默认超级用户就是 `postgres`，确认用 `-U postgres` 且容器名是 `irsbot-db-1` |
| 恢复后登录失败 | 确认 `.env` 的 `FIRST_SUPERUSER_PASSWORD` 与备份一致；启动时会把 `.env` 密码同步进库 |
| Milvus 起不来（etcd 锁） | 确认 `docker compose stop milvus` 已执行，且 `D:\Milvus\volumes\milvus\etcd` 没被别的进程占用 |
| 恢复向量目录后集合为空 | 拷贝路径错了——必须覆盖整个 `D:\Milvus\volumes\milvus`，不是子目录 |
| `backups/` 被 git 跟踪 | 已在备份脚本中自动加 `.gitignore`；若已误提交，从 git 移除：`git rm -r --cached backups` |

---

## 5. 相关脚本一览

| 脚本 | 作用 |
|---|---|
| `scripts/start.cmd` / `start.sh` | 一键启动（生成 `.env`、随机密码、构建、等健康、开浏览器） |
| `scripts/stop.cmd` / `stop.sh` | 停止（保留数据卷） |
| `scripts/reset.cmd` / `reset.sh` | 干净重来（`down -v` + start） |
| `scripts/backup.cmd` / `backup.ps1` | 一键只读备份（本文档第 1 节） |
| `scripts/bootstrap_env.ps1` | 首次引导：随机生成 SECRET_KEY / 管理员密码并写回 `.env` |
