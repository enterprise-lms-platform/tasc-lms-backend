# Subscription Status API — Frontend Integration Guide

## 1) Purpose

The platform is subscription-based. Learning content, enrollment, and participation in discussions require an active subscription. This endpoint is the **authoritative way** for the frontend to check whether the current user has entitlement to subscription-gated features.

## 2) Endpoint

| Property | Value |
|----------|-------|
| Method   | `GET` |
| Path     | `/api/v1/payments/subscription/me/` |
| Auth     | Bearer token required |

## 3) Response shape

### A) Active subscription (end_date present)

```json
{
  "has_active_subscription": true,
  "status": "active",
  "is_trial": false,
  "start_date": "2025-01-15T00:00:00Z",
  "end_date": "2025-07-15T23:59:59Z",
  "days_remaining": 131,
  "plan": {
    "id": 1,
    "name": "Pro Annual",
    "price": "99.00",
    "currency": "USD",
    "billing_cycle": "yearly"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `has_active_subscription` | boolean | Always `true` in this case |
| `status` | string | `"active"` |
| `is_trial` | boolean | Whether the subscription is a trial |
| `start_date` | string (ISO 8601) | Subscription start date |
| `end_date` | string (ISO 8601) | Subscription end date |
| `days_remaining` | int | Number of days until `end_date` (≥ 0) |
| `plan` | object | Plan details |

### B) Active subscription (end_date null)

When the subscription never expires, `end_date` and `days_remaining` are null:

```json
{
  "has_active_subscription": true,
  "status": "active",
  "is_trial": false,
  "start_date": "2025-01-15T00:00:00Z",
  "end_date": null,
  "days_remaining": null,
  "plan": {
    "id": 2,
    "name": "Enterprise",
    "price": "0.00",
    "currency": "USD",
    "billing_cycle": "lifetime"
  }
}
```

### C) No active subscription

```json
{
  "has_active_subscription": false,
  "status": "none",
  "is_trial": false,
  "start_date": null,
  "end_date": null,
  "days_remaining": 0,
  "plan": null
}
```

## 4) Frontend usage patterns

- **On app boot after login:** Call this endpoint once to determine entitlement.
- **Use `has_active_subscription`** to decide:
  - Show “Start course” vs “Subscribe”
  - Block navigation to learning content routes
  - Show subscription prompts or upgrade CTAs
- **Cache result** and refresh on key events:
  - User login
  - Subscription purchase / completion
  - Periodic refresh (e.g. every few minutes or on tab focus)

## 5) Status codes

| Code | Meaning |
|------|---------|
| 200 OK | Authenticated; response contains subscription status |
| 401 Unauthorized | Missing or invalid Bearer token |

## 6) Relationship to enrollment + content access

- **Enrollment create** requires an active subscription; otherwise returns `403 Forbidden`.
- **Session asset-url, progress, and discussions** require an active subscription; otherwise return `403 Forbidden`.
- **Public courses** remain accessible (browsing, metadata) without a subscription; only enrollment and learning content are gated.

## 7) Example curl

```bash
curl -X GET "https://api.example.com/api/v1/payments/subscription/me/" \
  -H "Authorization: Bearer <your_access_token>"
```
