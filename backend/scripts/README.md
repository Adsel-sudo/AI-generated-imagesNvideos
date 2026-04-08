# User maintenance scripts

Create user:

```bash
cd backend
python -m scripts.create_user <username> <password>
```

Reset password:

```bash
cd backend
python -m scripts.reset_password <username> <new_password>
```

Cleanup expired files:

```bash
python backend/scripts/cleanup_files.py
```

The script removes expired files under `data/uploads`, `data/outputs`, `data/zips`, and `data/logs` based on mtime retention rules.
