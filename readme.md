# TASC LMS Backend (Django + DRF)

This repository contains the backend for the **TASC Learning Management System (LMS)**, built using **Django**, **Django REST Framework**, and **JWT authentication**.

The goal of this backend is to provide a **secure, scalable, and well-documented API** that supports individual learners, organization-based learners, and internal TASC operations.

---

## 🚀 Current Status

**Milestone 1 – Authentication & User Management: ✅ COMPLETE**

The backend now has a stable authentication foundation and is ready for team-wide contribution.

---

## 🔐 Authentication Overview

The system uses **email-based authentication** (not username-based).

### Key Rules
- Users register using **email + password**
- New users are **inactive by default**
- Users **must verify their email** before logging in
- JWT is used for stateless authentication
- Default role on registration is **Learner**

---

## 🔄 Authentication Flow

1. **Register**
   - User submits registration details
   - Account is created with:
     - `email_verified = False`
     - `is_active = False`
   - Verification email is sent

2. **Verify Email**
   - User clicks verification link
   - Account becomes:
     - `email_verified = True`
     - `is_active = True`

3. **Login**
   - User logs in using **email + password**
   - JWT access & refresh tokens are returned
   - Login is blocked if email is not verified

---

## 🔗 Authentication API Endpoints

Base path: `/api/v1/auth/`

### Register
```
POST /api/v1/auth/register/
```
Creates a new user and sends a verification email.

**Request**
```json
{
  "email": "user@test.com",
  "password": "password",
  "confirm_password": "password",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+256700000000",
  "country": "Uganda",
  "timezone": "Nairobi",
  "accept_terms": true,
  "marketing_opt_in": false
}
```

---

### Verify Email
```
GET /api/v1/auth/verify-email/{uidb64}/{token}/
```

Activates the account and marks email as verified.

**Response**
```json
{
  "message": "Email verified successfully."
}
```

---

### Login (Email + Password)
```
POST /api/v1/auth/login/
```

**Request**
```json
{
  "email": "user@test.com",
  "password": "password"
}
```

**Response**
```json
{
  "refresh": "jwt-refresh-token",
  "access": "jwt-access-token",
  "user": { ... }
}
```

❗ Login will fail if:
- Email is not verified
- Account is inactive
- Credentials are invalid

---

### Refresh Token
```
POST /api/v1/auth/refresh/
```

**Request**
```json
{
  "refresh": "jwt-refresh-token"
}
```

---

### Current User
```
GET /api/v1/auth/me/
```

Returns the authenticated user's profile.

---

## 👤 User Model Summary

The custom `User` model extends `AbstractUser` with:

- `email` (unique, primary identifier)
- `role` (default: learner)
- `email_verified`
- `phone_number`
- `country`
- `timezone`
- `marketing_opt_in`
- `terms_accepted_at`

Usernames are **auto-generated** during registration.

---

## 🏢 Organizations (Foundation Ready)

Models already exist for:
- `Organization`
- `Membership`

Organizations:
- Do **not** create courses
- Only enroll staff to consume TASC courses
- Are managed by the TASC team

Implementation will follow in later milestones.

---

## 📚 API Documentation

Swagger / OpenAPI docs are available at:
```
/api/docs/
```

All authentication endpoints are fully documented and testable.

---

## 🧭 Contributor Guidelines

- **Do not modify auth logic** without team discussion
- Build features in the appropriate app:
  - `catalogue` → courses & categories
  - `learning` → enrollments, progress, certificates
  - `payments` → billing, invoices, transactions
- Use existing JWT authentication & permissions
- Document all new endpoints using drf-spectacular

---

## 🔜 Next Milestones

1. Course Catalogue
2. Enrollment & Learning Progress
3. Organization onboarding & staff management
4. Role-based permissions
5. Payments & reporting

---

## 🧠 Final Notes

This backend already provides:
- Production-grade authentication
- Secure email verification flow
- Clean API structure
- Clear separation of concerns

Treat authentication as the **core backbone** of the platform.

Happy building 🚀

