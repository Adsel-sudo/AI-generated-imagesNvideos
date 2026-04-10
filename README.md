# AI 电商生图平台（内部使用）

面向公司内部运营/投放团队的 AI 图片生成工作台。当前版本仅对外提供 **AI 生图能力**，用于快速生产电商图片素材。

> 说明：AI 视频方向已暂停开发；仓库内保留了部分底层兼容结构，但当前版本不对用户开放视频入口。

---

## 1. 项目定位

- **业务定位**：公司内部 AI 生图平台 / AI 图片生成工作台
- **当前状态**：AI 生图已可用并用于日常产出
- **部署形态**：Docker Compose 一体化部署，默认本地磁盘持久化
- **访问控制**：系统内账号登录（Session/Cookie）

---

## 2. 当前已实现能力

### 2.1 AI 生图主流程

- 根据自然语言需求创建生图任务
- 支持提示词优化后再生成
- 支持比例与分辨率选项（预设分辨率 + 自定义比例）
- 支持任务状态轮询（排队/处理中/完成/失败/取消）
- 支持生成结果文件输出与下载（单图下载 + 任务 ZIP 下载）

### 2.2 提示词优化能力

- 上传参考图：`POST /api/files`
- 优化提示词：`POST /api/prompt/optimize`
- 使用优化结果生成任务：`POST /api/prompt/generate-task`
- 支持参考图角色：商品图、构图图、姿势图、风格图
- 提示词优化会注入“主体身份保持”约束，降低商品主体漂移

### 2.3 前端工作台能力

- AI 图片工作台首页：`/`
- 会话式编辑与状态持久化
- 登录弹窗 + Session/Cookie 鉴权，未登录不可操作工作台
- 任务轮询与失败提示映射
- 生成结果预览与下载

---

## 3. 技术栈

### 后端

- **Python 3.11 + FastAPI**：任务创建、查询、下载、文件上传、提示词优化 API
- **Celery + Redis**：异步任务队列
- **SQLModel + SQLite（默认）**：任务与输出元数据存储
- **PostgreSQL（可选）**：长期运行场景可切换（见 `docker-compose.prod.yml`）

### 前端

- **Next.js 15 + React 19 + TypeScript + TailwindCSS**
- 当前仅保留 AI 生图工作台的用户可见入口

### 基础设施

- **Nginx 反向代理**：统一入口（`8080`），`/api` 转发到 FastAPI
- **Docker Compose**：本地/服务器场景可复用
- **本地文件存储**：`data/` 下持久化上传、输出、zip、日志、数据库

---

## 4. 关于 AI 视频能力（暂停）

- AI 视频功能目前 **暂停开发**，当前版本不对用户开放。
- 仓库中保留部分 video provider / schema / task_type 兼容结构，目的是降低后续恢复开发成本。
- 后续是否恢复视频能力，将根据业务需求再评估。

---

## 5. 快速启动（本地）

1. 准备环境变量：

```bash
cp .env.example .env
```

2. 启动服务：

```bash
docker compose up --build
```

3. 访问检查：

```bash
curl -I http://localhost:8080/
```

---

## 6. 仓库结构

- `backend/`：FastAPI API、数据模型、provider 路由、任务调度
- `worker/`：Celery worker 入口
- `frontend/`：Next.js AI 生图工作台
- `nginx/`：反向代理配置
- `data/`：本地持久化目录（上传/输出/压缩包/日志/数据库）
- `docker-compose.yml`：默认部署
- `docker-compose.prod.yml`：偏服务器化部署（含 PostgreSQL）

---

## 7. 文件/数据库定期清理（建议）

为控制磁盘增长并减少“文件已删但数据库仍有记录”的不一致，建议每日执行一次清理脚本：

```bash
python backend/scripts/cleanup_files.py --dry-run
python backend/scripts/cleanup_files.py
```

默认保留策略：

- 文件目录（按文件 mtime）：
  - `data/uploads`：14 天
  - `data/outputs`：30 天
  - `data/zips`：3 天
  - `data/logs`：14 天
- 数据库任务记录（按任务结束/更新时间）：
  - `failed/cancelled`：7 天
  - `done/completed/success/succeeded`：30 天
  - `queued/running/processing/pending/saving`：绝不清理

该脚本支持：

- `--dry-run`：仅输出将执行的动作，不实际删除
- 活跃任务引用的 upload 文件保护（避免误删仍在任务链路中的上传原图）
- 孤儿 `Output` 记录清理（`task_id` 不存在）
- 任务清理时优先删关联文件，再删 `Output` 与 `Task` 记录（保守策略）

Docker Compose 内执行方式：

```bash
docker compose exec api python /app/backend/scripts/cleanup_files.py --dry-run
docker compose exec api python /app/backend/scripts/cleanup_files.py
```

推荐使用宿主机 `cron` 调用容器内脚本，例如：

```cron
0 3 * * * docker compose exec -T api python /app/backend/scripts/cleanup_files.py --dry-run >> /var/log/ai-cleanup.log 2>&1
10 3 * * * docker compose exec -T api python /app/backend/scripts/cleanup_files.py >> /var/log/ai-cleanup.log 2>&1
```

上述配置表示每天凌晨 3:00 先 dry-run，3:10 再正式执行。

上线前自检清单：

- [ ] `.env` 中清理阈值已确认（含任务保留策略）
- [ ] 连续执行至少 2~3 次 `--dry-run`，确认删除候选符合预期
- [ ] 核对 active task 保护数量与 upload 引用保护数量日志
- [ ] 确认容器对 `data/` 目录具备读写/删除权限
- [ ] 确认清理日志会被持久化并可检索

上线后验证清单：

- [ ] 每日查看清理 summary（文件删除量、DB 删除量、跳过量）
- [ ] 监控 output 下载 404 比例是否异常
- [ ] 监控磁盘占用趋势（outputs/zips/logs）是否持续下降
- [ ] 抽样验证最近 24 小时活跃任务不受影响
- [ ] 出现异常时可先切回仅 dry-run（停正式清理）


---

## 8. 身份认证与安全建议

当前版本已启用账号登录与 Session/Cookie 鉴权（`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`）。

部署建议：

- 生产环境务必设置强密码并定期轮换账号密码。
- 配置反向代理与 HTTPS，避免明文传输登录会话。
- 建议仅开放公司内网访问，避免直接暴露到公网。
- 配合最小权限原则管理运维账号（创建/重置账号可使用 `backend/scripts/` 下脚本）。
