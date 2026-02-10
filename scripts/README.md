# Admin Scripts

Utility scripts for managing the XSW application.

## reset_admin_password.py

Reset admin user passwords in the database.

### Usage in Docker Container

After rebuilding the container, the script will be available at `/app/scripts/reset_admin_password.py`.

```bash
# List all admin users
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py --list

# Reset admin@localhost password to default 'admin'
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py

# Reset with custom email and password
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py \
  --email admin@localhost \
  --password newpass123
```

### Usage Without Rebuild (One-liner)

If you haven't rebuilt the container yet, use this one-liner:

```bash
docker exec xsw-xsw-1 python3 -c "
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

pwd_context = CryptContext(schemes=['argon2'], deprecated='auto')
engine = create_engine('sqlite:////app/data/xsw_cache.db')

email = 'admin@localhost'
new_password = 'admin'

with engine.connect() as conn:
    result = conn.execute(text('SELECT email FROM admin_users WHERE email = :email'), {'email': email})
    if result.fetchone():
        new_hash = pwd_context.hash(new_password)
        conn.execute(text('UPDATE admin_users SET password_hash = :hash WHERE email = :email'), {'hash': new_hash, 'email': email})
        conn.commit()
        print(f'✅ Password reset: {email} / {new_password}')
    else:
        print(f'❌ User {email} not found')
"
```

### Options

- `--db PATH` - Database path (default: /app/data/xsw_cache.db)
- `--email EMAIL` - Admin email (default: admin@localhost)
- `--password PASSWORD` - New password (default: admin)
- `--list` - List all admin users
- `--quiet` - Suppress output

### Examples

**Reset to default:**
```bash
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py
```

**List all users:**
```bash
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py --list
```

**Custom password:**
```bash
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py \
  --password "MySecurePass123!"
```

**Different user:**
```bash
docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py \
  --email user@example.com \
  --password "newpass"
```

## Current Status

✅ **Password already reset!**

The password for `admin@localhost` has been reset to `admin`.

**Login credentials:**
- Email: `admin@localhost`
- Password: `admin`
- URL: http://localhost:8000/

The script is available for future password resets after you rebuild the container.
