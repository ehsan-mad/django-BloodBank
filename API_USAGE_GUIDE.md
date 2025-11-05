# Blood Management API Usage Guide

This document explains how to interact with the Blood Management REST API that powers the Django blood bank application. It lists the available endpoints, the expected request payloads, typical responses, and the role-based access requirements.

> **Base URL**
>
> During local development the API is served at `http://localhost:8000/`. All endpoints below are shown relative to this base.

> **Authentication**
>
> The API uses JSON Web Tokens (JWT) issued by `/api/v1/auth/login/`. After logging in, supply the access token in the `Authorization` header using the `Bearer <token>` format for every protected endpoint.

---

## 1. Response Envelope

All views that call the helper functions in `accounts.utils` return data in the following wrapped format:

```json
// Success
{
  "status": "success",
  "message": "Human readable summary",
  "data": { /* endpoint-specific payload */ }
}
```

```json
// Error
{
  "status": "error",
  "message": "Explanation of what went wrong",
  "errors": { /* optional validation details */ }
}
```

Unless otherwise stated, failed requests return HTTP 4xx codes and successful requests return 2xx codes.

---

## 2. Health Check

| Method | Endpoint | Auth | Description |
| ------ | -------- | ---- | ----------- |
| GET | `/api/v1/health/` | Not required | Basic liveness probe. |

**Sample response**
```json
{
  "status": "ok",
  "version": "v1"
}
```

---

## 3. Authentication & User Management

### 3.1 Register
- **Endpoint:** `POST /api/v1/auth/register/`
- **Auth:** Not required
- **Use for:** Creating donor or admin accounts (role defaults to donor unless set manually via Django admin).

**Request body**
```json
{
  "username": "donor01",
  "email": "donor01@example.com",
  "password": "StrongPassword123!",
  "first_name": "Ayesha",
  "last_name": "Rahman",
  "blood_group": "O+",
  "city": "Dhaka",
  "contact": "+8801700000000"
}
```

On success the API sends a verification email (console backend in development) and returns the created user snapshot.

### 3.2 Verify Email
- **Endpoint:** `GET /api/v1/auth/email/verify/?token=<token>`
- **Auth:** Not required
- **Use for:** Completing email verification. The `token` parameter is included in the email generated during registration.

**Sample success response**
```json
{
  "status": "success",
  "message": "Email verified",
  "data": {
    "username": "donor01",
    "email": "donor01@example.com"
  }
}
```

### 3.3 Login
- **Endpoint:** `POST /api/v1/auth/login/`
- **Auth:** Not required
- **Use for:** Exchange username/password for JWT tokens. Email must be verified.

**Request body**
```json
{
  "username": "donor01",
  "password": "StrongPassword123!"
}
```

**Response**
```json
{
  "status": "success",
  "message": "Login successful",
  "data": {
    "refresh": "<refresh-token>",
    "access": "<access-token>"
  }
}
```

### 3.4 Logout
- **Endpoint:** `POST /api/v1/auth/logout/`
- **Auth:** Required (any authenticated user)
- **Use for:** Stateless logout. Client should discard tokens.

### 3.5 Profile
- **Endpoint:** `GET /api/v1/profile/`
- **Endpoint:** `PUT/PATCH /api/v1/profile/`
- **Auth:** Required

**Update payload (example)**
```json
{
  "first_name": "Ayesha",
  "last_name": "Rahman",
  "city": "Dhaka",
  "contact": "+8801700000000",
  "blood_group": "O+"
}
```

`username`, `email`, and `email_verified` are read-only in this endpoint.

---

## 4. Inventory & Donations ( `/api/v1/blood/…` )

> **Roles**
> * **Donor** – can create and view their own donation requests, view aggregated inventory.
> * **Admin** – can view everything, approve/reject donations, manage blood requests, and access the dashboard.

### 4.1 Inventory Levels
- **Endpoint:** `GET /api/v1/blood/inventory/`
- **Auth:** Required

**Sample response**
```json
{
  "status": "success",
  "message": "Inventory levels retrieved successfully",
  "data": [
    {
      "blood_group": "O+",
      "quantity": 18,
      "is_low": false,
      "last_updated": "2025-11-06T09:15:42.532Z"
    }
  ]
}
```

### 4.2 List Donations
- **Endpoint:** `GET /api/v1/blood/donations/`
- **Filters:** `status`, `start_date`, `end_date` (dates in `YYYY-MM-DD`)
- **Auth:** Required (donor sees own records, admin sees all)

### 4.3 Create Donation Request
- **Endpoint:** `POST /api/v1/blood/donations/create/`
- **Auth:** Donor role

**Request body**
```json
{
  "blood_group": "O+",
  "quantity": 1,
  "notes": "Available evenings only"
}
```

The donor is taken from the authenticated user and status is `pending` until an admin reviews it. Validation prevents donors from having overlapping pending requests or donations within the last 90 days.

### 4.4 Donation Detail
- **Endpoint:** `GET /api/v1/blood/donations/<id>/`
- **Auth:** Donor (own records) or admin

### 4.5 Approve/Reject Donation (Admin)
- **Endpoint:** `PATCH /api/v1/blood/donations/<id>/action/`
- **Auth:** Admin

**Request body**
```json
{
  "status": "approved", // or "rejected"
  "notes": "Screening passed"
}
```

Approving updates the inventory and creates an `InventoryTransaction` entry.

---

## 5. Blood Requests (Admin)

### 5.1 List Requests
- **Endpoint:** `GET /api/v1/blood/requests/`
- **Filters:** `status`, `urgency` (`true`/`false`), `start_date`, `end_date`
- **Auth:** Admin

### 5.2 Create Request
- **Endpoint:** `POST /api/v1/blood/requests/create/`

**Request body**
```json
{
  "blood_group": "A-",
  "quantity": 3,
  "patient_name": "Md Hasan",
  "hospital": "Dhaka Medical College",
  "urgency": true,
  "notes": "Surgery scheduled tomorrow"
}
```

`requested_by` is set from the authenticated admin user.

### 5.3 Request Detail
- **Endpoint:** `GET /api/v1/blood/requests/<id>/`
- **Auth:** Admin

### 5.4 Fulfill or Deny Request
- **Endpoint:** `PATCH /api/v1/blood/requests/<id>/action/`
- **Auth:** Admin

**Request body**
```json
{
  "status": "fulfilled", // or "denied"
  "notes": "Delivered to ward 5"
}
```

Fulfilling a request decrements inventory; the serializer validates available stock.

### 5.5 Admin Dashboard Snapshot
- **Endpoint:** `GET /api/v1/blood/dashboard/`
- **Auth:** Admin

Returns a combined view including:
- `inventory`: serialized inventory rows.
- `pending`: counts of pending donations and requests.
- `today`: counts of today’s approved donations and fulfilled requests.
- `recent_transactions`: up to 10 recent `InventoryTransaction` rows.
- `low_stock_alerts`: inventory items flagged as low.

---

## 6. Analytics Module ( `/api/v1/analytics/…` )

> **Note:** The view mixin currently allows all users while analytics features are under active development. In production, restrict to admins.

### 6.1 Dashboard Metrics
- **Endpoint:** `GET /api/v1/analytics/dashboard/metrics/`
- **Auth:** *(Intended)* Admin

**Sample response**
```json
{
  "donations_today": 4,
  "donations_this_week": 18,
  "donations_this_month": 54,
  "requests_today": 2,
  "requests_this_week": 9,
  "requests_this_month": 27,
  "critical_inventory": {
    "O-": 2
  },
  "expiring_soon": {}
}
```

Optional `*_error` fields may appear if underlying calculations fail.

### 6.2 Generate Reports
- **Endpoint:** `POST /api/v1/analytics/reports/generate/`
- **Auth:** *(Intended)* Admin

**Request body**
```json
{
  "report_type": "donation_summary",               // other choices: request_summary, inventory_summary, donation_trends, request_trends, inventory_forecast
  "start_date": "2025-10-01",
  "end_date": "2025-10-31",
  "format": "json",                                // optional: json (default), pdf, excel
  "blood_types": ["A+", "O-"],                    // optional filter
  "group_by": "week"                               // day (default), week, month
}
```

- `format = json` returns structured data in the standard response envelope.
- `format = pdf` or `excel` streams a downloadable report file.
- Use `?force_refresh=true` query param to bypass cached reports.

### 6.3 Chart Data
- **Endpoint:** `GET /api/v1/analytics/charts/data/`
- **Auth:** *(Intended)* Admin

Provide a `type` query parameter:

| Type | Required Query Parameters | Description |
| ---- | ------------------------ | ----------- |
| `donation_trend` | `start_date`, `end_date` (YYYY-MM-DD) | Line chart showing total/successful/rejected donations and success rate. |
| `blood_type_distribution` | *(none)* | Doughnut chart for latest inventory distribution. |
| `requests_fulfillment` | `start_date`, `end_date` | Pie chart for fulfilled/pending/cancelled requests. |
| `inventory_forecast` | `blood_type` | Line chart with historical levels and 7-day forecast for a specific blood type. |

**Example**
```
GET /api/v1/analytics/charts/data/?type=donation_trend&start_date=2025-10-01&end_date=2025-10-31
Authorization: Bearer <access>
```

---

## 7. Curl Examples

```bash
# Login and store access token
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "AdminPass123!"}'

# Use the returned access token
curl http://localhost:8000/api/v1/blood/inventory/ \
  -H "Authorization: Bearer <access-token>"

# Create a donation (donor token required)
curl -X POST http://localhost:8000/api/v1/blood/donations/create/ \
  -H "Authorization: Bearer <donor-access>" \
  -H "Content-Type: application/json" \
  -d '{"blood_group": "O+", "quantity": 1, "notes": "Available next week"}'
```

---

## 8. Troubleshooting Checklist

1. **401 Unauthorized:** Verify you included `Authorization: Bearer <access>` header and that the access token is not expired.
2. **403 Forbidden:** The authenticated user lacks the necessary role (e.g., donor accessing admin endpoint).
3. **400 Bad Request:** Inspect the `errors` object in the response for field-level validation messages.
4. **Email not verified:** Users must complete `/api/v1/auth/email/verify/` before login succeeds.
5. **Date validation errors (analytics):** Ensure the range is `<= 365` days and formatted as `YYYY-MM-DD`.

---

## 9. Extending the API

- Add new endpoints under the appropriate app (`accounts`, `donations`, or `analytics`).
- Maintain the response wrapper for consistency.
- Update this guide whenever routes or request schemas change to keep client integrations in sync.

---

*Last updated: 2025-11-06*
