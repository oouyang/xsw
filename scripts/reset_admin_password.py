#!/usr/bin/env python3
"""
Reset admin user password in the database.

Usage:
    # In Docker container:
    docker exec xsw-xsw-1 python3 /app/scripts/reset_admin_password.py

    # Locally:
    python3 scripts/reset_admin_password.py

    # With custom email and password:
    python3 scripts/reset_admin_password.py --email admin@localhost --password newpass123
"""
import argparse
import sys
import os
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

# Initialize password context (must match auth.py)
pwd_context = CryptContext(schemes=['argon2'], deprecated='auto')

def reset_password(db_path: str, email: str, new_password: str, verbose: bool = True):
    """Reset password for an admin user."""
    # Connect to database
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.connect() as conn:
        # Check if user exists
        result = conn.execute(
            text('SELECT email, auth_method, is_active FROM admin_users WHERE email = :email'),
            {'email': email}
        )
        user = result.fetchone()

        if not user:
            if verbose:
                print(f'❌ User {email} not found')
                print()
                print('Available users:')
                result = conn.execute(text('SELECT email, auth_method, is_active FROM admin_users'))
                for u in result.fetchall():
                    status = '✓ active' if u[2] else '✗ inactive'
                    print(f'  - {u[0]} ({u[1]}) [{status}]')
            return False

        # Check if password auth
        if user[1] != 'password':
            if verbose:
                print(f'❌ User {email} uses {user[1]} authentication, not password')
                print('   Password reset only works for password-based auth')
            return False

        # Generate new password hash
        new_hash = pwd_context.hash(new_password)

        # Update password
        conn.execute(
            text('UPDATE admin_users SET password_hash = :hash WHERE email = :email'),
            {'hash': new_hash, 'email': email}
        )
        conn.commit()

        if verbose:
            print('✅ Password reset successful!')
            print()
            print('Login credentials:')
            print(f'  Email:    {user[0]}')
            print(f'  Password: {new_password}')
            print(f'  Active:   {"Yes" if user[2] else "No"}')
            print()

        return True

def list_users(db_path: str):
    """List all admin users."""
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT email, auth_method, is_active, created_at, last_login_at FROM admin_users')
        )
        users = result.fetchall()

        if not users:
            print('No admin users found in database')
            return

        print(f'Found {len(users)} admin user(s):')
        print()
        for u in users:
            status = '✓ active' if u[2] else '✗ inactive'
            print(f'Email:      {u[0]}')
            print(f'Auth:       {u[1]}')
            print(f'Status:     {status}')
            print(f'Created:    {u[3] or "N/A"}')
            print(f'Last login: {u[4] or "Never"}')
            print()

def main():
    parser = argparse.ArgumentParser(
        description='Reset admin user password',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset admin@localhost password to 'admin'
  %(prog)s

  # Reset specific user with custom password
  %(prog)s --email user@example.com --password mypass123

  # List all admin users
  %(prog)s --list
        """
    )
    parser.add_argument(
        '--db',
        default=os.getenv('DB_PATH', '/app/data/xsw_cache.db'),
        help='Path to SQLite database (default: /app/data/xsw_cache.db)'
    )
    parser.add_argument(
        '--email',
        default='admin@localhost',
        help='Admin email address (default: admin@localhost)'
    )
    parser.add_argument(
        '--password',
        default='admin',
        help='New password (default: admin)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all admin users and exit'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress output except errors'
    )

    args = parser.parse_args()

    # Check if database exists
    if not os.path.exists(args.db):
        print(f'❌ Database not found: {args.db}')
        return 1

    # List users mode
    if args.list:
        list_users(args.db)
        return 0

    # Reset password mode
    success = reset_password(
        db_path=args.db,
        email=args.email,
        new_password=args.password,
        verbose=not args.quiet
    )

    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
