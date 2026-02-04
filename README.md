# TASC LMS Backend (Django + DRF)

This repository contains the backend for the **TASC Learning Management System (LMS)**, built using **Django**, **Django REST Framework**, and **JWT authentication**. The goal of this backend is to provide a **secure, scalable, and well-documented API** that supports individual learners, organization-based learners, and internal TASC operations.

---

## 🎯 Current Status

**Milestone 1 & 2 – Core Infrastructure & Features: ✅ COMPLETE**

The backend is now **100% ready for frontend integration**. All core models, serializers, and API views have been implemented across the four main modules: Accounts, Catalogue, Learning, and Payments.

---

## 🔐 Authentication & User Management

The system uses **email-based authentication** (not username-based).

### Key Rules
- Users register using **email + password**
- New users are **inactive by default**
- Users **must verify their email** before logging in
- **JWT** is used for stateless authentication
- Default role on registration is **Learner**
- **Google OAuth** is fully integrated for social login

### Authentication API Endpoints
Base path: `/api/v1/auth/`

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `register/` | POST | Creates a new user and sends a verification email. |
| `login/` | POST | Login with email/password; returns access/refresh tokens. |
| `refresh/` | POST | Exchange refresh token for a new access token. |
| `me/` | GET | Returns the authenticated user's profile. |
| `verify-email/<uidb64>/<token>/` | GET | Activates the account and marks email as verified. |
| `google/login/` | POST | Google OAuth authentication using ID token. |
| `google/link/` | POST | Link a Google account to an existing user account. |
| `google/unlink/` | POST | Unlink a Google account from the user. |
| `google/status/` | GET | Check Google OAuth linking status. |

---

## 🗺️ Project Structure

The project is organized into modular apps to ensure clear separation of concerns:

| App | Responsibility | Key Models |
| :--- | :--- | :--- |
| **Accounts** | Identity & Access | `User`, `Organization`, `Membership` |
| **Catalogue** | Course Content | `Course`, `Category`, `Session`, `Tag` |
| **Learning** | Progress Tracking | `Enrollment`, `SessionProgress`, `Certificate`, `Discussion` |
| **Payments** | Billing & Finance | `Invoice`, `Transaction`, `Subscription`, `PaymentMethod` |
| **Common** | Shared Utilities | Health check endpoints, shared mixins |

---

## 📚 Feature Highlights

### 1. Course Catalogue
- **Hierarchical Categories**: Organize courses into parent and child categories.
- **Rich Content**: Support for video, text, and live sessions.
- **Search & Filtering**: Filter courses by category, tag, instructor, and price.

### 2. Learning Management
- **Progress Tracking**: Automatic percentage calculation based on session completion.
- **Certificates**: Automated PDF certificate generation upon course completion.
- **Social Learning**: Threaded discussions and replies for courses and sessions.

### 3. Payments & Subscriptions
- **Flexible Billing**: Support for individual course purchases and subscription plans.
- **Invoicing**: Detailed invoice generation with line items and status tracking.
- **Payment Methods**: Securely save and manage multiple payment methods.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL (for production)
- Google OAuth Credentials (for social login)

### Installation
1. Clone the repository and navigate to the project root.
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment: `source venv/bin/activate` (Linux/macOS) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt,pip install --upgrade setuptools ,python.exe -m pip install --upgrade pip`
5. Set up your environment variables in a `.env` file (see `.env.example`).
6. Run migrations: `python manage.py migrate`
7. Start the development server: `python manage.py runserver`

### Environment Variables
Key variables required in your `.env` file:
- `DJANGO_SECRET_KEY`: Your unique secret key.
- `DJANGO_DEBUG`: Set to `True` for development.
- `GOOGLE_OAUTH2_CLIENT_ID` & `GOOGLE_OAUTH2_CLIENT_SECRET`: For social login.
- `CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed frontend domains.

---

## 📖 API Documentation

The API is fully documented using **drf-spectacular**. You can access the interactive documentation at:

- **Swagger UI**: `http://127.0.0.1:8000/api/docs/`
- **ReDoc**: `http://127.0.0.1:8000/api/redoc/`
- **OpenAPI Schema**: `http://127.0.0.1:8000/api/schema/`

All endpoints include request/response schemas, parameter descriptions, and example payloads.

---

## 🤝 Contributor Guidelines

- **API First**: Always document new endpoints using `drf-spectacular` decorators.
- **Separation of Concerns**: Place logic in the appropriate app.
- **Security**: Use existing JWT authentication and role-based permissions.
- **Testing**: Write unit tests for new models and API views.

Happy building 🚀