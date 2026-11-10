# Telecom Prepaid REST API

A REST API backend for managing prepaid telecom operations, built with **Python, FastAPI, SQLAlchemy, and PostgreSQL**.

This project simulates the backend of a fictional mobile network operator (MVNO). It provides APIs for customer registration, subscriber management, prepaid plans, recharges, complaints, usage records, and operational analytics.

The project focuses on API design, database modelling, authentication, role-based access control, data validation, and automated testing.

## Key Features

- **Authentication:** JWT-based login and user registration.
- **Role-based access control:** Separate admin, staff, and user permissions.
- **Subscriber management:** Create, retrieve, update, search, and close subscriber records.
- **Prepaid plans:** Plan listing, filtering, searching, creation, updating, and deactivation.
- **Recharge management:** Recharge creation and duplicate-reference protection.
- **Complaint management:** Complaint creation, source tracking, and status updates.
- **Usage records:** Store subscriber usage information.
- **Analytics:** Operational summary endpoint.
- **Validation and error handling:** Structured request validation and centralized API error responses.
- **Rate limiting:** Protect API endpoints from excessive requests.
- **Database support:** PostgreSQL for containerized development and SQLite for local development.
- **Database migrations:** Alembic migration setup.
- **Automated tests:** Pytest-based API tests.
- **API documentation:** Interactive Swagger UI and generated OpenAPI specification.
- **Load testing scenario:** k6 test script for evaluating plan endpoint performance.

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python |
| API framework | FastAPI |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Database | PostgreSQL / SQLite |
| Authentication | JWT |
| Password hashing | Passlib |
| Database migrations | Alembic |
| Testing | Pytest |
| Rate limiting | SlowAPI |
| Containerization | Docker and Docker Compose |
| Load testing | k6 |

## Architecture

The application separates API handling, business logic, database access, and configuration.

```mermaid

flowchart TD

&#x20;   Client\[Web / Mobile / Postman]

&#x20;   API\[FastAPI API Layer]

&#x20;   Auth\[JWT Authentication and RBAC]

&#x20;   Service\[Business Logic / Services]

&#x20;   Repo\[Repository Helpers]

&#x20;   DB\[(PostgreSQL / SQLite)]

&#x20;   Client --> API

&#x20;   API --> Auth

&#x20;   Auth --> Service

&#x20;   Service --> Repo

&#x20;   Repo --> DB

```

### Project Structure

```text

telecom-prepaid-rest-api/

â”‚

â”œâ”€â”€ app/

â”‚   â”œâ”€â”€ core.py

â”‚   â”œâ”€â”€ main.py

â”‚   â”œâ”€â”€ models.py

â”‚   â”œâ”€â”€ repositories.py

â”‚   â”œâ”€â”€ schemas.py

â”‚   â”œâ”€â”€ security.py

â”‚   â”œâ”€â”€ seed.py

â”‚   â””â”€â”€ services.py

â”‚

â”œâ”€â”€ migrations/

â”‚   â””â”€â”€ versions/

â”‚

â”œâ”€â”€ tests/

â”‚   â””â”€â”€ test_api.py

â”‚

â”œâ”€â”€ load/

â”‚   â””â”€â”€ k6-plans.js

â”‚

â”œâ”€â”€ openapi/

â”œâ”€â”€ postman/

â”‚

â”œâ”€â”€ .env.example

â”œâ”€â”€ .gitignore

â”œâ”€â”€ Dockerfile

â”œâ”€â”€ docker-compose.yml

â”œâ”€â”€ alembic.ini

â”œâ”€â”€ pyproject.toml

â””â”€â”€ requirements.txt

```

## Getting Started

### Prerequisites

- Python 3.11 or compatible version supported by the project dependencies.
- Git.
- Docker Desktop with Docker Compose, if using the containerized setup.

### Option 1: Run with Docker Compose

Clone the repository:

```bash

git clone https://github.com/prashanthreddy-134/telecom-prepaid-rest-api.git

cd telecom-prepaid-rest-api

```

Create your environment file:

```bash

copy .env.example .env

```

Generate a secure secret key:

```bash

python -c "import secrets; print(secrets.token_urlsafe(48))"

```

Set the generated value as `SECRET_KEY` in `.env`. Keep this value private. Do not commit `.env`.

Start the application:

```bash

docker compose up --build

```

### Option 2: Run Locally with SQLite

Create and activate a virtual environment:

```powershell

python -m venv venv

.\\venv\\Scripts\\Activate.ps1

```

Install dependencies:

```powershell

python -m pip install -r requirements.txt

```

Create your local environment file:

```powershell

Copy-Item .env.example .env

```

Edit `.env` and configure:

```dotenv

DATABASE_URL=sqlite:///./telecom.db

SECRET_KEY=replace-with-your-own-long-random-secret

RATE_LIMIT=120/minute

```

Initialize the demo data:

```powershell

python -m app.seed

```

Start the API:

```powershell

uvicorn app.main:app --reload

```

If database initialization is managed separately in your local configuration, apply the appropriate Alembic migration before starting the application.

## API Documentation

Once the application is running:

| Resource | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| Health check | http://localhost:8000/health |
| Readiness check | http://localhost:8000/ready |

Swagger UI allows you to inspect endpoints, submit requests, and test authenticated operations.

## API Modules

The API includes 28 documented routes across these modules:

| Module | Capabilities |
|---|---|
| Authentication | Registration, login, current-user details |
| Plans | Search, filter, pagination, details, create, update, deactivate |
| Circles | Search, pagination, details, create, update, delete |
| Subscribers | Search, filter, pagination, details, create, update, close |
| Recharges | List and create |
| Complaints | List, create, status updates |
| Usage | List and create |
| Analytics | Operational summary |
| System | Health and readiness checks |

Refer to the live OpenAPI specification for the exact endpoint paths, HTTP methods, request schemas, and response formats.

## Demo Accounts

The seed data provides the following local testing accounts:

| Role | Email | Password |
|---|---|---|
| Admin | admin@demo.local | AdminPass123! |
| Staff | staff@demo.local | StaffPass123! |
| User | user@demo.local | UserPass123! |

**Security warning:** These are development-only credentials. Never use them in production or expose them on a deployed public instance.

## Data Modelling and Validation

The application includes several domain-specific data rules:

- Monetary values are represented as integer paise to avoid floating-point currency calculations.
- Data quotas and usage are represented in MB.
- GB ingestion uses the conversion 1 GB = 1024 MB.
- Subscriber lifecycle states include `active`, `suspended`, `ported_out`, and `closed`.
- Complaint records preserve their source channel and source-specific external references.
- Recharge references are unique to prevent duplicate submissions.
- Foreign keys maintain circle and subscriber relationships.
- Seed data includes a correction for a stale subscriber status; real production systems should rely on verified porting events rather than name-based assumptions.

## Testing

Run the automated test suite:

```powershell

python -m pytest -q

```

For coverage reporting:

```powershell

coverage run -m pytest

coverage report

```

The project has previously passed **24 automated tests** in the development environment. Run the tests again against the current checkout to confirm the result.

A coverage target of 75% or higher is a project goal, not a measured result claimed by this repository.

## Load Testing

A k6 scenario is provided:

```bash

k6 run -e BASE_URL=http://localhost:8000 load/k6-plans.js

```

The scenario is configured to target:

- 200 requests per second.
- 60 seconds of execution.
- p95 response time below 300 ms.
- Error rate below 1%.

These are configured test thresholds, not verified production performance results. Actual results depend on hardware, database configuration, and deployment environment.

## Current Limitations and Future Improvements

This project is a development and learning baseline, not a production-certified telecom platform.

Potential improvements include:

- Implement Redis cache-aside behaviour for plan endpoints, including cache invalidation on plan updates.
- Complete an ownership audit across all subscriber, complaint, and usage endpoints.
- Validate database migration and rollback procedures in deployment.
- Add refresh-token rotation and revocation.
- Integrate a real payment provider and verified payment callbacks.
- Add TLS, centralized secrets management, and audit logging.
- Implement account lockout and request correlation IDs.
- Measure and improve test coverage and load-test performance.

Recharge ownership was manually tested for the recharge creation flow. That does not constitute a complete authorization audit of every end-user endpoint.

## Repository

GitHub: https://github.com/prashanthreddy-134/telecom-prepaid-rest-api

## Author

**Prashanth Reddy**
