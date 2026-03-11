# 2FA Recovery Guide

This guide explains how to recover access for users who have lost their 2FA (Two-Factor Authentication) setup.

## Quick Reference

Run this command to see all available recovery options:
```bash
python manage.py help_2fa
```

## Recovery Scenarios

### Scenario 1: User Lost Authenticator App Access
**Problem**: User enabled 2FA but deleted the app or lost their phone.

**Solution**: Disable 2FA for the user
```bash
python manage.py disable_2fa <username_or_email>
```

**Admin UI**: Go to `/admin/` → Users → Select user → Actions → "Disable 2FA for selected users"

### Scenario 2: User Forgot Password
**Problem**: User forgot their password.

**Solution**: Reset password (will email temporary password)
```bash
python manage.py reset_password <username_or_email>
```

**Admin UI**: Go to `/admin/` → Users → Select user → Actions → "Reset passwords for selected users"

### Scenario 3: Both Issues
**Problem**: User lost 2FA access AND forgot password.

**Solution**: Run both commands
```bash
python manage.py disable_2fa <username_or_email>
python manage.py reset_password <username_or_email>
```

## Security Best Practices

- **Verify Identity**: Always confirm the user's identity before running recovery commands
- **Admin Only**: These commands should only be run by trusted administrators
- **Audit Logs**: Check server logs for command usage
- **User Communication**: Inform users when their 2FA is disabled or password is reset

## Admin Interface Features

The Django admin interface (`/admin/`) now includes:

- **User List View**: Shows 2FA status for each user
- **Bulk Actions**: Select multiple users and disable 2FA or reset passwords
- **Staff Edit Page**: Clean, organized interface with:
  - **Personal & Contact Information** card (name, email, phone, address details)
  - **Account Status & Permissions** card (login/active toggles, 2FA status/controls, user groups)
  - **Banking Information** card (payment details)

## Prevention

To avoid future recovery needs:
- Encourage users to backup their authenticator app data
- Consider using backup codes (future enhancement)
- Educate users on 2FA best practices