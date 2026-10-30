# O’Toosin Farms Production Deployment

Production target: `https://otoosinfarms.com.ng`

This guide covers a single-instance Django deployment using SQLite, Gunicorn,
WhiteNoise and a reverse proxy (Rimbra or any equivalent Python host). No
secrets belong in this file or in git. Store real values in the hosting
provider's secret/environment settings.

## 1. Host requirements

- Python 3.12 or 3.13.
- One Gunicorn process, or multiple worker processes on one host only.
- Persistent writable storage for:
  - the SQLite database (`SQLITE_PATH`),
  - uploaded product images (`MEDIA_ROOT`).
- HTTPS terminating at the reverse proxy or platform edge.
- Ability to run release commands and restart the app.
- Outbound HTTPS access to `api.resend.com` and `api.paystack.co`.

SQLite is approved for this project, but it is not suitable for multiple
application servers or horizontally scaled instances. Keep the database and
media on a persistent volume and never rebuild the filesystem without restoring
them.

## 2. Environment configuration

The project uses one environment file only: `.env` in the project root. It is
already ignored by git and contains the local test keys. Do not create a second
env file and do not upload `.env` to the repository.

For production, copy the same key names into the hosting platform's
environment/secret manager and replace the local values:

```dotenv
DEBUG=False
SECRET_KEY=<long random secret>
ALLOWED_HOSTS=otoosinfarms.com.ng,www.otoosinfarms.com.ng
CSRF_TRUSTED_ORIGINS=https://otoosinfarms.com.ng,https://www.otoosinfarms.com.ng
SITE_URL=https://otoosinfarms.com.ng
RESEND_API_KEY=<production Resend key>
RESEND_FROM_EMAIL=O’Toosin Farms <no-reply@otoosinfarms.com.ng>
SUPPORT_EMAIL=support@otoosinfarms.com.ng
PAYSTACK_SECRET_KEY=<live Paystack secret key>
PAYSTACK_PUBLIC_KEY=<live Paystack public key>
SQLITE_PATH=/data/db.sqlite3
STATIC_ROOT=/data/staticfiles
MEDIA_ROOT=/data/media
```

The remaining keys in the local `.env` (`RESEND_API_URL`,
`RESEND_TIMEOUT_SECONDS`, `STAFF_INVITATION_HOURS`, `PASSWORD_RESET_TIMEOUT`,
`PAYSTACK_BASE_URL`, `PAYSTACK_TIMEOUT_SECONDS`, `STATIC_URL`, `MEDIA_URL`,
`TIME_ZONE`, security/cookie values, WhiteNoise and logging) should also be
copied to the host. Only the values that differ between local and production
need changing.

Important:

- `SITE_URL` must be the exact public HTTPS origin. Invitation, reset and email
  logo links are built from it.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` must include the exact production
  hostnames. Do not use `*`.
- Generate `SECRET_KEY` once and keep it stable:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

- Production startup intentionally fails if `SECRET_KEY`, `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `RESEND_API_KEY` or
  `RESEND_FROM_EMAIL` are missing or invalid.
- SSL redirect and secure session/CSRF cookies follow `DEBUG` automatically:
  off locally, on when `DEBUG=False`. Do not force them to `False` in the host
  environment.
- When the platform terminates TLS and forwards `X-Forwarded-Proto`, set
  `USE_X_FORWARDED_PROTO=True`. Otherwise Django may redirect in a loop.
- Keep `SECURE_HSTS_SECONDS=0` until HTTPS and all subdomains are verified.
  Then raise it gradually, for example `300`, `86400`, then `31536000`, and
  only then enable `SECURE_HSTS_INCLUDE_SUBDOMAINS`/`SECURE_HSTS_PRELOAD`.
- If the host has persistent disk for logs, set `DJANGO_LOG_FILE` so warnings
  and errors survive restarts. Container logs alone are acceptable when the
  platform retains them.

## 3. Release commands

Run these on every deploy, in this order:

```bash
python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py provision_staff_roles
```

`collectstatic` must complete without errors before `check --deploy` or app
startup: production storage uses a manifest, and the app resolves static URLs at
import time. Static files are served by WhiteNoise from `STATIC_ROOT`; the
reverse proxy does not need a separate static directory. Uploaded media is
served by the app from `MEDIA_ROOT`.

`check --deploy` should report only warnings you have consciously accepted. A
`SECURE_HSTS_SECONDS` warning is expected until the HSTS rollout in section 2.
A weak `SECRET_KEY` warning means the production secret is not ready; replace
it before launch.

Start the app with:

```bash
gunicorn Otoosin_project.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
```

Use the platform's documented start command instead where it supplies one.
Keep worker count low with SQLite, and never run multiple app instances against
the same SQLite file.

## 4. First owner account

After the first deploy and migrations:

```bash
python manage.py createsuperuser
python manage.py provision_staff_roles
```

Then sign in at `/staff/login/`, confirm the owner account has the Owner role,
and invite the remaining team from `/staff/team/`. Do not create shared staff
accounts. Invitations and password resets use branded Resend emails and expire
automatically.

## 5. Resend email setup

1. Add and verify `otoosinfarms.com.ng` in Resend.
2. Publish the DNS records Resend provides (SPF and DKIM at minimum). Add DMARC
   when the domain's mail policy is ready.
3. Verify the sender address. `RESEND_FROM_EMAIL` must use the verified domain;
   `RESEND_API_KEY` must be the production key, not a test key.
4. Set `SITE_URL=https://otoosinfarms.com.ng` so the email logo resolves to
   `https://otoosinfarms.com.ng/static/assets/img/harvest_castle/of_favicon.png`.
5. Send one staff invitation and one password reset to a controlled inbox.
   Check the branded HTML, plain-text fallback, link host and expiry text.

Email failures are persisted in `EmailDelivery`. Staff invitations can be
resent from `/staff/team/`; do not claim delivery succeeded unless the provider
accepted the request.

## 6. Paystack live payment checklist

1. Complete Paystack merchant approval for O’Toosin Farms.
2. Replace test keys with live keys in the host secret manager only:
   `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY`.
3. Confirm the callback/webhook URL points at the production domain and that
   the live webhook secret matches.
4. Place one low-value live order, verify payment status server-side, confirm
   the order appears in staff orders, and refund/cancel the test transaction
   according to Paystack policy.
5. Do not enable or advertise live payment until `DEPLOY-001` sign-off.

## 7. Backups and restore

Back up both the database and uploaded media; either alone is not a complete
restore.

SQLite online backup:

```bash
sqlite3 /data/db.sqlite3 ".backup '/backups/otoosin-$(date +%Y%m%d-%H%M%S).sqlite3'"
```

Media backup:

```bash
tar -czf "/backups/otoosin-media-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data media
```

Retain at least daily backups off the application host, encrypt them, and test
a restore on a staging copy. Restore procedure:

```bash
# Stop the app first so no writes occur during the restore.
cp /backups/otoosin-YYYYMMDD-HHMMSS.sqlite3 /data/db.sqlite3
tar -xzf /backups/otoosin-media-YYYYMMDD-HHMMSS.tar.gz -C /data
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# Start the app and run the smoke test.
```

Also back up `.env`/secret-manager values separately and securely.

## 8. Post-deploy smoke test

Run in a private browser window:

- `https://otoosinfarms.com.ng/` loads over HTTPS with no mixed-content or
  static-file errors.
- Shop, category, search, product detail and cart work on mobile and desktop.
- Checkout validates the cart, creates one order, redirects to Paystack and
  returns to a verified confirmation.
- A failed/cancelled payment does not show as paid.
- Staff login works; a test invitation and password reset arrive and activate
  correctly; `/staff/products/`, `/staff/orders/`, `/staff/settings/` load.
- A contact message is stored and appears in the staff inbox.
- The branded 404 and 500 pages render without tracebacks when `DEBUG=False`.
- `python manage.py check --deploy` has no unexplained warnings.
- Logs show the request and no secret values.

## 9. Rollback

Keep the previous release and a pre-deploy database backup. To roll back:

1. Stop the app.
2. Restore the matching database and media backup if migrations changed data.
3. Deploy the previous code revision and previous environment values.
4. Run `python manage.py migrate --noinput` only if the previous revision is
   compatible with the restored database.
5. Run `python manage.py collectstatic --noinput`, restart and repeat the smoke
   test.

Do not roll back only the code while keeping an incompatible database schema.
