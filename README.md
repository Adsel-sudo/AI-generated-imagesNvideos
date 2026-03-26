# AI 电商素材平台（内部使用）

面向公司内部运营/投放团队的 AI 素材生产平台，当前重点支持 **AI 生图**，并已完成 AI 视频能力的基础架构预留。

> 使用场景：内部小规模并发（通常不超过 5 人）下，快速生成电商图片素材，后续扩展到视频素材并迁移到服务器长期运行。

---

## 1. 项目定位

- **业务定位**：电商素材生产中台（内部工具）
- **当前阶段**：AI 生图功能已可用；AI 视频功能处于“页面占位 + 后端 provider 预留”阶段
- **部署形态**：Docker Compose 一体化部署，默认本地磁盘持久化
- **访问控制**：Nginx Basic Auth（适合内部环境）

---

## 2. 技术栈总览

### 后端

- **Python 3.11 + FastAPI**：提供任务创建、查询、下载、文件上传、提示词优化等 API
- **Celery + Redis**：异步任务队列（生成任务在 worker 中执行）
- **SQLModel + SQLite（默认）**：任务与输出元数据存储
- **PostgreSQL（可选）**：为服务器长期运行预留（见 `docker-compose.prod.yml`）
- **Pydantic Settings**：集中管理环境变量与模型路由配置

### AI 能力层（Provider Router）

- `google_image`：已接入主流程（基于 `google-genai`）
- `prompt_optimizer`：已接入，用于把自然语言需求优化为结构化生成提示词
- `google_video`：已注册但 `generate` 仍为 `NotImplementedError`（待开发）
- 兼容别名：`gemini`、`veo`、`mock`

### 前端

- **Next.js 15 + React 19 + TypeScript + TailwindCSS**
- 现状：
  - AI 图片工作台（`/`）已接入完整交互流程
  - AI 视频页（`/video`）为占位页，明确“后续上线”

### 基础设施

- **Nginx 反向代理**：统一入口（`8080`），将 `/api` 转发到 FastAPI，其余请求转发到前端
- **Docker Compose**：本地与服务器迁移都可复用
- **本地文件存储**：上传、输出、zip、日志、数据库均在 `data/` 下持久化

---

## 3. 当前已实现功能（AI 生图）

### 3.1 任务与素材管理

- 创建任务：`POST /api/tasks`
- 查询任务列表：`GET /api/tasks`
- 查询任务详情（含 outputs / outputs_by_target）：`GET /api/tasks/{task_id}`
- 取消任务：`POST /api/tasks/{task_id}/cancel`
- 下载单个输出：`GET /api/tasks/{task_id}/outputs/{output_id}`
- 下载任务打包 ZIP：`GET /api/tasks/{task_id}/download.zip`

### 3.2 提示词优化链路

- 上传参考图：`POST /api/files`
- 优化提示词：`POST /api/prompt/optimize`
- 用优化结果创建任务：`POST /api/prompt/generate-task`
- 支持参考图角色：商品图、构图图、姿势图、风格图
- 支持多目标输出（不同比例/尺寸/产出数量）

### 3.3 前端工作台能力

- 会话式编辑与状态持久化
- 参考图上传与分类限制
- 任务轮询、状态反馈、失败映射
- 生成结果预览与下载
- 顶部导航（AI 图片 / AI 视频）

---

## 4. AI 视频开发进度说明

当前仓库已完成“可扩展骨架”，但尚未进入可用状态：

1. **已完成**
   - 前端 `/video` 页面与导航入口
   - 后端 `google_video` provider 注册
   - 视频相关通用字段已在 schema/model 中预留（如 `duration_seconds`, `fps`）
   - 系统级视频模型配置项已就位：`GOOGLE_VIDEO_MODEL`（默认 `veo-3.1-fast-generate-001`）

2. **未完成（下一阶段）**
   - `google_video` 的真实 `generate` 实现（目前会抛出 `NotImplementedError`）
   - 视频任务参数标准化与校验策略
   - 视频输出文件写入、封面/时长元数据回填、下载体验优化
   - 视频页完整交互（输入区、任务列表、播放预览、下载）

---

## 5. 结合当前业务规模（并发 ≤ 5）建议

### 当前可行方案（短期）

- 继续沿用现有架构：FastAPI + Celery + Redis + SQLite
- 单机 Docker Compose 部署即可满足内部使用
- 建议为 `data/` 目录配置定期备份（至少备份 `db/`、`outputs/`、`uploads/`）

### 迁移服务器时建议（中期）

- 将数据库切换为 PostgreSQL（直接使用 `docker-compose.prod.yml` 思路）
- 对 `data/` 做独立磁盘挂载与容量监控
- 通过环境变量统一管理模型名和密钥
- 保留 Nginx Basic Auth 作为第一层防护；若后续外网开放，再补充 SSO / 网关鉴权

---

## 6. 快速启动（本地）

1. 准备环境变量：

```bash
cp .env.example .env
```

2. 启动服务：

```bash
docker compose up --build
```

3. 健康检查（需 Basic Auth）：

```bash
curl -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASSWORD" http://localhost:8080/health
```

---

## 7. 近期 Roadmap（建议）

### Milestone A：AI 视频 MVP（优先）

- [ ] 实现 `google_video` provider 的 text-to-video 主链路
- [ ] 接通 `/video` 页面任务创建、轮询、预览、下载
- [ ] 增加视频任务失败重试与更清晰错误提示

### Milestone B：服务器稳定化

- [ ] 切换 PostgreSQL
- [ ] 增加日志分级与错误告警
- [ ] 增加定期清理策略（过期任务、临时文件、zip）

### Milestone C：生产化增强（按需）

- [ ] 增加权限分层（运营/审核）
- [ ] 增加素材标签、检索与复用
- [ ] 对接对象存储（S3/OSS）替代本地磁盘

---

## 8. 仓库结构

- `backend/`：FastAPI API、数据模型、provider 路由、任务调度
- `worker/`：Celery worker 入口
- `frontend/`：Next.js 前端工作台
- `nginx/`：反向代理与 Basic Auth
- `data/`：本地持久化目录（上传/输出/压缩包/日志/数据库）
- `docker-compose.yml`：本地/默认部署
- `docker-compose.prod.yml`：偏服务器化部署（含 PostgreSQL）
