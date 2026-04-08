# User maintenance scripts

这些脚本直接修改数据库 `user` 表，执行后**立即生效**，不需要重启 docker 服务。

## 推荐在服务器中的执行方式

```bash
docker compose exec api bash
cd /app/backend
```

> 说明：在当前项目结构下，`cd /app/backend` 后使用 `python scripts/*.py ...` 的方式最稳定，可避免 `No module named 'app'` / `No module named 'scripts'` 导入问题。

## 新增账号

```bash
python scripts/create_user.py <username> <password>
```

- 不存在时创建并输出：`[CREATED] <username>`
- 已存在时不重复创建并输出：`[EXISTS] <username>`

## 重置密码

```bash
python scripts/reset_password.py <username> <new_password>
```

- 存在时更新密码并输出：`[UPDATED] <username>`
- 不存在时输出：`[NOT FOUND] <username>`，并返回非 0 退出码

## 删除账号

```bash
python scripts/delete_user.py <username>
```

- 存在时删除并输出：`[DELETED] <username>`
- 不存在时输出：`[NOT FOUND] <username>`，并返回非 0 退出码

## 列出账号

```bash
python scripts/list_users.py
```

输出格式示例：

```text
total=3
alice
bob
carol
```

仅输出用户名，不输出 `password_hash`。

## 可选：模块方式执行

如果你的运行目录和 `PYTHONPATH` 配置正确，也可以用模块方式：

```bash
python -m backend.scripts.create_user <username> <password>
python -m backend.scripts.reset_password <username> <new_password>
python -m backend.scripts.delete_user <username>
python -m backend.scripts.list_users
```
