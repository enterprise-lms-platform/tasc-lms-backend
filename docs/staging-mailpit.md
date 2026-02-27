# Staging OTP Email Testing with Mailpit

Use Mailpit in staging to capture all outbound emails (including OTP) without bypassing MFA/OTP security.

## Docker Compose Service

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    container_name: mailpit
    restart: unless-stopped
    ports:
      - "8025:8025" # Web UI
      - "1025:1025" # SMTP
```

## Staging `.env` Values

```env
EMAIL_PROVIDER=django
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_USE_SSL=False
```

Optional if your SMTP catcher requires auth:

```env
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

## How to View OTP Emails

Open Mailpit UI:

`http://<droplet-ip>:8025`

You can log in normally and inspect OTP emails sent to any address.

## Behavior Notes

- OTP stays always-on.
- No OTP bypass is introduced.
- All staging emails are captured by Mailpit even when recipient addresses look real.
