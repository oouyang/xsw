# Google OAuth2 SSO Setup Guide

This guide walks you through setting up Google OAuth2 Single Sign-On (SSO) for the admin panel authentication.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Google Cloud Console Setup](#google-cloud-console-setup)
4. [Backend Configuration](#backend-configuration)
5. [Frontend Configuration](#frontend-configuration)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)
8. [Security Best Practices](#security-best-practices)
9. [Emergency Access](#emergency-access)

---

## Overview

The admin panel now supports two authentication methods:

1. **Google OAuth2 SSO** (Primary, Recommended)
   - Secure authentication via Google accounts
   - No password management required
   - Email whitelist for access control

2. **Password Authentication** (Fallback, Emergency Access Only)
   - Email/password login
   - Default admin account: `admin@example.com` / `admin`
   - Hidden in UI, available in collapsible section

---

## Prerequisites

- Google account for authentication setup
- Access to [Google Cloud Console](https://console.cloud.google.com/)
- Domain or public URL for your application (required for production)
- Admin access to the application server

---

## Google Cloud Console Setup

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown (top left, next to "Google Cloud")
3. Click **"New Project"**
4. Enter project name (e.g., "xsw-admin-auth")
5. Click **"Create"**
6. Wait for the project to be created and select it

### Step 2: Enable Google+ API

1. In the left sidebar, navigate to **APIs & Services** > **Library**
2. Search for **"Google+ API"**
3. Click on **"Google+ API"** in the search results
4. Click **"Enable"**
5. Wait for the API to be enabled

### Step 3: Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Select **"External"** user type (unless you have Google Workspace)
3. Click **"Create"**

4. **Fill in App Information:**
   - **App name**: "看小說 Admin Panel" (or your app name)
   - **User support email**: Your email address
   - **App logo**: (Optional) Upload your app logo
   - **Application home page**: Your application URL (e.g., `https://yourdomain.com`)
   - **Application privacy policy link**: (Optional) Your privacy policy URL
   - **Application terms of service link**: (Optional) Your ToS URL
   - **Authorized domains**: Add your domain (e.g., `yourdomain.com`)
   - **Developer contact information**: Your email address

5. Click **"Save and Continue"**

6. **Scopes (Step 2):**
   - Click **"Add or Remove Scopes"**
   - Select the following scopes:
     - `openid`
     - `https://www.googleapis.com/auth/userinfo.email`
     - `https://www.googleapis.com/auth/userinfo.profile`
   - Click **"Update"**
   - Click **"Save and Continue"**

7. **Test users (Step 3):**
   - Click **"Add Users"**
   - Add email addresses that should have admin access (e.g., `admin@example.com`)
   - Click **"Add"**
   - Click **"Save and Continue"**

8. **Summary (Step 4):**
   - Review your settings
   - Click **"Back to Dashboard"**

### Step 4: Create OAuth2 Credentials

1. Navigate to **APIs & Services** > **Credentials**
2. Click **"Create Credentials"** at the top
3. Select **"OAuth client ID"**

4. **Configure OAuth Client:**
   - **Application type**: Select **"Web application"**
   - **Name**: "xsw-admin-web-client" (or any name you prefer)

5. **Authorized JavaScript origins:**
   - Click **"Add URI"**
   - For local development: `http://localhost:9000` (or your dev port)
   - For production: `https://yourdomain.com`
   - Add multiple URIs if needed (dev, staging, production)

6. **Authorized redirect URIs:**
   - Google Sign-In doesn't require explicit redirect URIs for ID token flow
   - You can leave this empty or add your domain

7. Click **"Create"**

8. **Copy Your Credentials:**
   - A dialog will appear with your **Client ID** and **Client Secret**
   - **IMPORTANT**: Copy the **Client ID** (it looks like `123456789-abc123.apps.googleusercontent.com`)
   - You don't need the Client Secret for this implementation
   - Click **"OK"**

9. You can view your Client ID anytime by clicking on the credential name in the credentials list

---

## Backend Configuration

### Step 1: Install Python Dependencies

If not already installed, add the required packages:

```bash
pip install PyJWT>=2.8.0 passlib[bcrypt]>=1.7.4 google-auth>=2.28.0
```

Or install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

Create or edit your `.env` file in the project root:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=123456789-abc123.apps.googleusercontent.com

# Admin Email Whitelist (comma-separated)
ADMIN_EMAIL_WHITELIST=admin@example.com,user2@example.com,user3@example.com

# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET=your-random-secret-here-generate-with-openssl-rand-hex-32

# JWT Token Expiration (hours)
JWT_EXPIRATION_HOURS=24
```

#### Generate JWT Secret

Run this command to generate a secure random secret:

```bash
openssl rand -hex 32
```

Copy the output and paste it as the `JWT_SECRET` value.

#### Configure Email Whitelist

Add the email addresses that should have admin access to `ADMIN_EMAIL_WHITELIST`:

- Use comma-separated format: `email1@domain.com,email2@domain.com`
- Only these emails will be able to authenticate via Google SSO
- Test users from OAuth consent screen should be included here

### Step 3: Database Migration

The `AdminUser` table will be created automatically when the application starts. The default admin user (`admin@example.com` / `admin`) will also be created if no admin users exist.

### Step 4: Restart the Application

Restart your application to load the new environment variables:

```bash
# If using Docker Compose
docker-compose restart

# Or rebuild if needed
docker-compose up -d --build

# If running directly
# Kill the existing process and restart
```

---

## Frontend Configuration

### Step 1: Install Frontend Dependencies

If not already installed:

```bash
npm install jwt-decode
```

### Step 2: Configure Frontend Environment Variables

Create or edit `.env.local` in the project root (frontend):

```bash
# Google OAuth Client ID (same as backend)
VITE_GOOGLE_CLIENT_ID=123456789-abc123.apps.googleusercontent.com
```

**IMPORTANT**: Use the same Client ID from Google Cloud Console.

### Step 3: Build Frontend

Rebuild the frontend to include the new configuration:

```bash
npm run build
```

For development:

```bash
npm run dev
```

---

## Testing

### Test 1: Google Sign-In Flow

1. Open the application in a browser
2. Click on the admin panel button (gear icon or admin menu)
3. You should see:
   - **"Sign in with Google"** button (prominent)
   - **"OR"** separator
   - **"Password Login (Fallback)"** expandable section

4. Click **"Sign in with Google"**
5. A Google popup should appear
6. Sign in with an email from your `ADMIN_EMAIL_WHITELIST`
7. After successful authentication:
   - The admin panel should open
   - You should see your Google profile picture (if available)
   - Your email should be displayed
   - A green chip with "Google" label should show your auth method

### Test 2: Password Login (Fallback)

1. Expand the **"Password Login (Fallback)"** section
2. Enter:
   - **Email**: `admin@example.com`
   - **Password**: `admin` (default, change immediately!)
3. Click **"Login"**
4. The admin panel should open
5. You should see:
   - Default account icon (no profile picture)
   - Email: `admin@example.com`
   - A grey chip with "Password" label

### Test 3: Protected Endpoints

1. Open browser DevTools (F12) and go to Network tab
2. In the admin panel, trigger an action (e.g., "Refresh" stats)
3. Check the request headers for `/admin/*` endpoints
4. You should see: `Authorization: Bearer <long-token-string>`
5. Without authentication, `/admin/*` endpoints should return 401

### Test 4: Token Expiration

1. Log in via Google or password
2. Wait 24 hours (or modify `JWT_EXPIRATION_HOURS` to 1 minute for testing)
3. Try to access an admin function
4. You should be logged out automatically
5. You'll need to log in again

### Test 5: Email Whitelist

1. Try to sign in with a Google account NOT in `ADMIN_EMAIL_WHITELIST`
2. You should see an error: "Google Sign-In failed"
3. Check browser console for: "Email not authorized for admin access"
4. Only whitelisted emails should be able to authenticate

---

## Troubleshooting

### Issue 1: "redirect_uri_mismatch" Error

**Symptoms**: Google OAuth popup shows "redirect_uri_mismatch" error.

**Solution**:

1. Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
2. Click on your OAuth 2.0 Client ID
3. Verify **Authorized JavaScript origins** includes your current URL:
   - Development: `http://localhost:9000` (or your port)
   - Production: `https://yourdomain.com`
4. Save changes and wait 5 minutes for propagation
5. Clear browser cache and try again

### Issue 2: Google Sign-In Button Not Appearing

**Symptoms**: No Google button shows up, only password login visible.

**Possible Causes & Solutions**:

1. **Missing Client ID**:
   - Check `.env.local` has `VITE_GOOGLE_CLIENT_ID` set
   - Verify the value matches Google Cloud Console
   - Restart the dev server: `npm run dev`

2. **Script Loading Failed**:
   - Open browser console (F12)
   - Check for errors loading `https://accounts.google.com/gsi/client`
   - Ensure no ad blockers are blocking Google scripts
   - Check network connectivity

3. **Container Element Issue**:
   - Check browser console for: "Failed to initialize Google Sign-In"
   - The `googleButtonContainer` ref might not be available
   - Refresh the page

### Issue 3: "Google Sign-In failed" After Successful Google Login

**Symptoms**: Google popup succeeds, but admin panel shows error.

**Possible Causes & Solutions**:

1. **Email Not Whitelisted**:
   - Check backend `.env` file has `ADMIN_EMAIL_WHITELIST`
   - Verify your email is in the list (comma-separated, no spaces)
   - Restart the backend after changing `.env`

2. **Backend GOOGLE_CLIENT_ID Mismatch**:
   - Verify backend `.env` has correct `GOOGLE_CLIENT_ID`
   - Must match the frontend `VITE_GOOGLE_CLIENT_ID`
   - Must match Google Cloud Console Client ID
   - Restart backend after changes

3. **Backend Error**:
   - Check backend logs for authentication errors
   - Look for: "Invalid Google token" or "Email not authorized"
   - Verify `google-auth` Python package is installed

### Issue 4: "401 Unauthorized" on Admin Endpoints

**Symptoms**: Admin functions fail with 401 errors.

**Possible Causes & Solutions**:

1. **Token Expired**:
   - Tokens expire after 24 hours (default)
   - Log out and log in again
   - Token will be automatically cleared on 401

2. **Missing Authorization Header**:
   - Check Network tab in DevTools
   - `/admin/*` requests should have `Authorization: Bearer <token>`
   - Verify axios interceptor is working
   - Clear localStorage and log in again

3. **JWT Secret Changed**:
   - If `JWT_SECRET` changed in `.env`, old tokens are invalid
   - Log out and log in again
   - Consider this when deploying to production

### Issue 5: "Token has expired" or "Invalid token"

**Symptoms**: Immediate logout after login, or constant 401 errors.

**Possible Causes & Solutions**:

1. **Server/Client Time Mismatch**:
   - Ensure server and client clocks are synchronized
   - Check server time: `date` on server
   - JWT tokens are time-sensitive

2. **JWT Secret Mismatch**:
   - Verify `.env` has `JWT_SECRET` set
   - Ensure it's the same across all backend instances (if load balanced)
   - Generate a new secret if needed: `openssl rand -hex 32`

3. **Token Storage Issue**:
   - Clear browser localStorage: DevTools > Application > Local Storage > Clear
   - Log in again

---

## Security Best Practices

### 1. JWT Secret Management

- **Generate Strong Secret**: Always use `openssl rand -hex 32` to generate JWT_SECRET
- **Never Commit Secrets**: Add `.env` to `.gitignore`
- **Rotate Regularly**: Consider rotating JWT_SECRET periodically (invalidates all tokens)
- **Environment-Specific**: Use different secrets for dev, staging, production

### 2. Email Whitelist

- **Principle of Least Privilege**: Only add emails that absolutely need admin access
- **Regular Audits**: Review and update the whitelist monthly
- **Remove Departing Users**: Immediately remove emails when users leave
- **Use Corporate Emails**: Prefer corporate email addresses over personal ones

### 3. HTTPS in Production

- **Always Use HTTPS**: OAuth2 requires HTTPS in production
- **Authorized Origins**: Only add HTTPS URLs to Google Cloud Console
- **SSL Certificates**: Use Let's Encrypt or similar for free SSL
- **HTTP Redirect**: Configure server to redirect HTTP to HTTPS

### 4. Token Expiration

- **Short Expiration**: Default 24 hours is reasonable
- **For High Security**: Set `JWT_EXPIRATION_HOURS=8` (work day)
- **Refresh Mechanism**: Consider implementing refresh tokens for longer sessions

### 5. Password Authentication

- **Change Default Password**: Immediately change `admin@example.com` / `admin` in production
- **Strong Passwords**: Minimum 12 characters, mix of upper/lower/numbers/symbols
- **Consider Disabling**: In production, consider disabling password auth entirely (Google SSO only)
- **Emergency Access Only**: Treat password login as last resort

### 6. Rate Limiting

- The application already has rate limiting configured
- Monitor rate limit stats in admin panel
- Adjust limits based on your needs in `.env`

### 7. Audit Logging

- Monitor backend logs for authentication attempts
- Log failed login attempts
- Set up alerts for suspicious activity (e.g., many failed attempts)

### 8. Regular Updates

- Keep dependencies updated:
  ```bash
  pip install --upgrade PyJWT google-auth passlib
  npm update jwt-decode
  ```
- Monitor security advisories for these packages
- Test thoroughly after updates

---

## Emergency Access

### Scenario 1: Lost Google Account Access

If you lose access to your Google account:

1. Use password authentication (fallback)
2. Expand "Password Login (Fallback)" section
3. Log in with `admin@example.com` / `admin` (or your changed password)
4. This works even if Google SSO is unavailable

### Scenario 2: Forgot Password

If you forgot the password for `admin@example.com`:

1. Access the server directly (SSH or console)
2. Run Python shell:
   ```bash
   python
   ```
3. Reset password:

   ```python
   from db_models import db_manager, AdminUser
   from auth import hash_password

   session = db_manager.get_session()
   admin = session.query(AdminUser).filter_by(email='admin@example.com').first()
   if admin:
       admin.password_hash = hash_password('new-password-here')
       session.commit()
       print("Password reset successfully")
   else:
       print("Admin user not found")
   session.close()
   ```

4. Log in with the new password

### Scenario 3: Locked Out Completely

If you can't access Google SSO or password login:

1. Access server directly
2. Add your email to `ADMIN_EMAIL_WHITELIST` in `.env`
3. Restart the application
4. Use Google Sign-In with your newly whitelisted email

### Scenario 4: Database Corruption

If the `AdminUser` table is corrupted:

1. Access server
2. Delete the database file (SQLite):
   ```bash
   rm xsw.db  # or your database file name
   ```
3. Restart application (will recreate database with default admin)
4. Log in with `admin@example.com` / `admin`
5. Immediately change the default password

---

## Advanced Configuration

### Multiple Environments

For dev, staging, and production environments:

**Development (.env.dev)**:

```bash
GOOGLE_CLIENT_ID=dev-client-id.apps.googleusercontent.com
ADMIN_EMAIL_WHITELIST=dev@example.com
JWT_SECRET=dev-secret-change-me
JWT_EXPIRATION_HOURS=24
```

**Production (.env.prod)**:

```bash
GOOGLE_CLIENT_ID=prod-client-id.apps.googleusercontent.com
ADMIN_EMAIL_WHITELIST=admin@company.com,manager@company.com
JWT_SECRET=<strong-production-secret>
JWT_EXPIRATION_HOURS=8
```

### Disabling Password Authentication

To disable password login entirely (Google SSO only):

1. Comment out the password expansion section in `AdminDialog.vue`
2. Or add a feature flag in config to hide password login
3. Keep emergency access via server console for password reset

### Custom Token Expiration

Adjust based on your security requirements:

```bash
# Development (long sessions)
JWT_EXPIRATION_HOURS=168  # 1 week

# Production (short sessions)
JWT_EXPIRATION_HOURS=4    # 4 hours

# High Security
JWT_EXPIRATION_HOURS=1    # 1 hour
```

### Monitoring Authentication

Add monitoring to track:

- Failed login attempts
- Token expirations
- Google SSO vs password login usage
- Admin actions by email/auth method

---

## FAQ

**Q: Can I use multiple Google Client IDs?**
A: No, use one Client ID per environment. Create separate OAuth clients in Google Cloud Console for dev/staging/production.

**Q: Is the default password `admin` secure?**
A: No. It's for initial setup only. Change it immediately or use Google SSO exclusively.

**Q: Can I use Google Workspace accounts?**
A: Yes. Configure OAuth consent screen as "Internal" for Workspace-only access.

**Q: What happens if GOOGLE_CLIENT_ID is not set?**
A: Google Sign-In button won't appear. Password login will still work.

**Q: Can I have admins with different permission levels?**
A: Currently, all admins have full access. RBAC (role-based access control) is a future enhancement.

**Q: How do I revoke access for a user?**
A: Remove their email from `ADMIN_EMAIL_WHITELIST` and restart the backend. Existing tokens will expire within 24 hours (or your configured JWT_EXPIRATION_HOURS).

**Q: Is it safe to commit .env.local with VITE_GOOGLE_CLIENT_ID?**
A: Client IDs are not secrets (they're visible in browser anyway), but it's still best practice to gitignore `.env.local` and document the required variables.

**Q: Can users change their password via the UI?**
A: Yes, if authenticated via password. The "Change Password" button appears for password-authenticated users.

**Q: What if I want to add more OAuth providers (GitHub, etc.)?**
A: The architecture supports this. Add new methods to `authService.ts` and backend `auth.py`, then add buttons to `AdminDialog.vue`.

---

## Support

For issues or questions:

1. Check [Troubleshooting](#troubleshooting) section
2. Review backend logs for error details
3. Open an issue on the project repository
4. Contact the development team

---

## Changelog

- **2025-01-29**: Initial Google OAuth2 SSO implementation
  - Added Google Sign-In as primary auth method
  - Password authentication as fallback
  - JWT-based backend authentication
  - Email whitelist for access control
