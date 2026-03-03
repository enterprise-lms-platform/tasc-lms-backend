📘 TASC LMS – Staging, Mailpit & Seeder Guide
# TASC LMS – Staging, Mailpit & Seeder Guide

This document explains:

1. Why we introduced Mailpit
2. How email works across environments (Dev / Staging / Prod)
3. How to use the `seed_staging` command
4. Safe deployment workflow to staging
5. Common pitfalls and fixes
6. Quick cheat sheet commands

---

# 1️⃣ Why We Introduced Mailpit

Previously:
- Emails were printed to console in development.
- OTP emails were not easily inspectable in staging.
- Real email providers (SendGrid) were risky in staging.

We introduced **Mailpit** as a local SMTP email catcher.

Mailpit:
- Captures all outgoing emails.
- Does NOT send emails to real users.
- Provides a web UI to inspect emails.
- Perfect for OTP testing, invites, verification flows.

---

# 2️⃣ Email Architecture Per Environment

## 🖥 Development (Local)

Django runs with:


EMAIL_PROVIDER=django
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1025


Mailpit runs locally:


docker compose -f docker-compose.local.yml up -d


Mailpit UI:

http://127.0.0.1:8025


Result:
- All emails appear in Mailpit.
- No emails leave your machine.

---

## 🌐 Staging (Droplet)

Staging `.env`:


EMAIL_PROVIDER=django
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025


Mailpit runs as Docker service:


mailpit:
image: axllent/mailpit:latest
ports:
- "8025:8025"
- "1025:1025"


Result:
- All staging emails captured by Mailpit.
- Safe OTP testing.
- No real emails sent.

---

## 🚀 Production (Future)

Production should use:


EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=...


Mailpit is NOT used in production.

---

# 3️⃣ The `seed_staging` Command

Purpose:
Create realistic demo data for staging or development.

---

## Always Created (User Cohorts)

Default seed creates:

- 50 learners
- 15 instructors
- 5 lms_managers
- 3 finance
- 2 tasc_admin
- 2 org_admin

Emails follow pattern:


learner1@test.com

instructor1@test.com

manager1@test.com

admin1@test.com

finance1@test.com


Default password:

Pass12345!


Users are:
- is_active=True
- email_verified=True

---

## Optional: Catalogue Seeding


python manage.py seed_staging --with-catalogue


Creates:
- Categories (2-level hierarchy)
- Tags
- Courses (slug prefixed with `seed-`)
- Sessions

Published course requirements enforced:
- Non-empty thumbnail
- >= 4 learning objectives
- Sessions created

---

## Optional: Enrollment Seeding


python manage.py seed_staging --with-enrollments


Now restricted to:
- Published courses only

Ensures:

Enrollment.objects.exclude(course__status="published").count() == 0


---

## Optional: Progress + Certificates


python manage.py seed_staging --with-progress --with-certificates


Creates:
- SessionProgress records
- Certificates for sufficiently completed enrollments

---

## Full Demo Dataset


python manage.py seed_staging --reset
python manage.py seed_staging
--with-catalogue
--with-enrollments
--with-progress
--with-certificates


---

# 4️⃣ Deployment Workflow to Staging

## Step 1 – Pull latest code


git pull origin main


## Step 2 – Backup DB


docker compose -f docker-compose.staging.yml exec -T db
pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql


## Step 3 – Rebuild


docker compose -f docker-compose.staging.yml up -d --build


## Step 4 – Run migrations


docker compose -f docker-compose.staging.yml exec web python manage.py migrate


## Step 5 – Seed data


docker compose -f docker-compose.staging.yml exec web python manage.py seed_staging --with-catalogue --with-enrollments


---

# 5️⃣ Bugs We Fixed During This Phase

## Decimal * Float TypeError

Original issue:

Decimal * float -> TypeError


Fixed by:
- Using Decimal arithmetic only in `discounted_price`
- Added unit tests

Lesson:
Always keep monetary calculations in Decimal.

---

## Seeder Enrolling Into Draft Courses

Fixed by:
Restricting enrollment pool to:

Course.objects.filter(status="published")


Lesson:
Demo data must reflect production rules.

---

# 6️⃣ Cheat Sheet

## Start Mailpit (local)

docker compose -f docker-compose.local.yml up -d


## View emails

http://127.0.0.1:8025


## Reset seed data

python manage.py seed_staging --reset


## Create full demo dataset

python manage.py seed_staging --with-catalogue --with-enrollments --with-progress --with-certificates


## Verify no draft enrollments

Enrollment.objects.exclude(course__status="published").count()


---

# 7️⃣ Environment Philosophy

Development:
- Flexible
- Local mail capture
- SQLite allowed

Staging:
- Production-like
- PostgreSQL
- Mailpit capture
- Realistic seeded data

Production:
- No seeders
- Real email provider
- Strict security

---

# Final Notes

Mailpit was introduced to:
- Improve OTP testing
- Avoid sending real emails from staging
- Provide safe email visibility

The seed_staging command ensures:
- Predictable demo users
- Realistic course catalogue
- Demo-ready enrollments
- Clean resets

This setup allows safe, scalable staging environments without technical debt.