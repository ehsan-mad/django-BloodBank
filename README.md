# Blood Management API

A Django REST Framework service for managing blood bank operations, including donor registrations, donation tracking, blood requests, inventory analytics, and administrative workflows. This README provides the high-level overview, local setup steps, and the complete API usage guide needed to integrate with the service.

---

## Features

- JWT-secured REST API with donor and admin roles.
- Donation intake workflow with approval and inventory reconciliation.
- Hospital blood request management and fulfillment tracking.
- Analytics endpoints for dashboards, trends, and forecast reports.
- Fully documented responses wrapped in a consistent status/message envelope.

---

## Prerequisites

- Python 3.10+
- MySQL 8 (for local development; fallback to SQLite if unavailable)
- Node/npm (optional, only if you plan to work on the frontend bundle)

Clone the repository and create a virtual environment:

```powershell
cd C:\dev\django
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies and configure the environment:

```powershell
pip install -r requirements.txt
copy .env.template .env  # update values as needed
```

Then apply migrations and run the development server:

```powershell
python manage.py migrate
python manage.py runserver
```

The API defaults to `http://localhost:8000/`.

---

## API Usage Guide

All endpoints live under `/api/v1/…`. Authenticated routes expect a JWT `Authorization: Bearer <token>` header unless otherwise noted.

> **Response Envelope**  
> Views that call `accounts.utils` helpers respond with:
>
> - Success:
>   ```json
>   {
>     "status": "success",
>     "message": "Human readable summary",
>     "data": { }
>   }
>   ```
> - Error:
>   ```json
>   {
>     "status": "error",
>     "message": "Explanation of what went wrong",
>     "errors": { }
>   }
>   ```

### Health Check

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

### Authentication & User Management

#### Register
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

#### Verify Email
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

#### Login
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

#### Logout
- **Endpoint:** `POST /api/v1/auth/logout/`
- **Auth:** Required (any authenticated user)
- **Use for:** Stateless logout. Client should discard tokens.

#### Profile
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

### Inventory & Donations (`/api/v1/blood/…`)

> **Roles**  
> - **Donor** – can create and view their own donation requests, view aggregated inventory.  
> - **Admin** – can view everything, approve/reject donations, manage blood requests, and access the dashboard.

#### Inventory Levels
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

#### List Donations
- **Endpoint:** `GET /api/v1/blood/donations/`
- **Filters:** `status`, `start_date`, `end_date` (dates in `YYYY-MM-DD`)
- **Auth:** Required (donor sees own records, admin sees all)

#### Create Donation Request
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

#### Donation Detail
- **Endpoint:** `GET /api/v1/blood/donations/<id>/`
- **Auth:** Donor (own records) or admin

#### Approve/Reject Donation (Admin)
- **Endpoint:** `PATCH /api/v1/blood/donations/<id>/action/`
- **Auth:** Admin

**Request body**
```json
{
  "status": "approved",
  "notes": "Screening passed"
}
```

Approving updates the inventory and creates an `InventoryTransaction` entry.

### Blood Requests (Admin)

#### List Requests
- **Endpoint:** `GET /api/v1/blood/requests/`
- **Filters:** `status`, `urgency` (`true`/`false`), `start_date`, `end_date`
- **Auth:** Admin

#### Create Request
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

#### Request Detail
- **Endpoint:** `GET /api/v1/blood/requests/<id>/`
- **Auth:** Admin

#### Fulfill or Deny Request
- **Endpoint:** `PATCH /api/v1/blood/requests/<id>/action/`
- **Auth:** Admin

**Request body**
```json
{
  "status": "fulfilled",
  "notes": "Delivered to ward 5"
}
```

Fulfilling a request decrements inventory; the serializer validates available stock.

#### Admin Dashboard Snapshot
- **Endpoint:** `GET /api/v1/blood/dashboard/`
- **Auth:** Admin

Returns a combined view including inventory, pending counts, today9s metrics, recent transactions, and low-stock alerts.

### Analytics Module (`/api/v1/analytics/…`)

> **Note:** The view mixin currently allows all users while analytics features are under active development. In production, restrict to admins.

#### Dashboard Metrics
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

#### Generate Reports
- **Endpoint:** `POST /api/v1/analytics/reports/generate/`
- **Auth:** *(Intended)* Admin

**Request body**
```json
{
  "report_type": "donation_summary",
  "start_date": "2025-10-01",
  "end_date": "2025-10-31",
  "format": "json",
  "blood_types": ["A+", "O-"],
  "group_by": "week"
}
```

- `format = json` returns structured data in the standard response envelope.
- `format = pdf` or `excel` streams a downloadable report file.
- Use `?force_refresh=true` query param to bypass cached reports.

#### Chart Data
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

### Curl Examples

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

## Troubleshooting Checklist

1. **401 Unauthorized:** Verify you included `Authorization: Bearer <access>` and that the token is valid.
2. **403 Forbidden:** The authenticated user lacks the necessary role (e.g., donor accessing admin endpoint).
3. **400 Bad Request:** Inspect the `errors` object for field-level validation messages.
4. **Email not verified:** Users must complete `/api/v1/auth/email/verify/` before login succeeds.
5. **Date validation errors (analytics):** Ensure the range is `<= 365` days and formatted as `YYYY-MM-DD`.

---

## Contributing

- Follow PEP 8 and project linting rules.
- Maintain the response envelope when adding endpoints.
- Update `API_USAGE_GUIDE.md` (mirrors this README) whenever payloads or routes change.

---

*Last updated: 2025-11-06*
