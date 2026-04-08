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
- 支持任务状态轮询（排队/处理中/完成/失败/取消）
- 支持生成结果文件输出与下载（单图下载 + 任务 ZIP 下载）

### 2.2 提示词优化能力

- 上传参考图：`POST /api/files`
- 优化提示词：`POST /api/prompt/optimize`
- 使用优化结果生成任务：`POST /api/prompt/generate-task`
- 支持参考图角色：商品图、构图图、姿势图、风格图

### 2.3 前端工作台能力

- AI 图片工作台首页：`/`
- 会话式编辑与状态持久化
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
