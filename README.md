# Telecom Prepaid REST API

A production-oriented REST API for managing telecom prepaid services, built with **FastAPI, Python, SQLAlchemy, PostgreSQL, Redis, JWT authentication, and Docker**.

The application supports prepaid plan management, subscriber lifecycle management, recharges, usage tracking, complaints, role-based access control, analytics, caching, and automated testing.

It also includes a k6 load-testing setup to measure API performance under sustained traffic.

---

## Project Highlights

- RESTful API built using FastAPI.
- JWT-based authentication.
- Role-based access control for Admin, Staff, and User.
- PostgreSQL database with SQLAlchemy ORM.
- Pydantic v2 request and response validation.
- Redis caching for public plan endpoints.
- Cache invalidation using generation-based keys.
- Database fallback when Redis is unavailable.
- API rate limiting using SlowAPI.
- Structured request logging and error handling.
- Database migrations using Alembic.
- Automated testing using pytest.
- Code coverage reporting using pytest-cov.
- Docker Compose infrastructure.
- Performance testing using Grafana k6.

## Performance Benchmark

**Verified local Docker benchmark:**

| Metric | Result | Target |
|---|---:|---:|
| Throughput | 200.00 requests/sec | 200 requests/sec |
| Total requests | 12,001 | — |
| Test duration | 60 seconds | 60 seconds |
| Average latency | 3.63 ms | — |
| p95 latency | 6.39 ms | Below 300 ms |
| Maximum latency | 33.21 ms | — |
| Failed requests | 0% | Below 1% |
| Dropped iterations | 0 | — |

All configured k6 performance thresholds passed.

**Benchmark scope:** Local Docker environment, testing the public plans listing endpoint. These results are not a production capacity guarantee and do not represent every API endpoint.

## Technology Stack

| Category | Technology |
|---|---|
| Language | Python |
| Backend | FastAPI |
| ORM | SQLAlchemy |
| Validation | Pydantic v2 |
| Database | PostgreSQL |
| Cache | Redis |
| Authentication | JWT |
| Password Hashing | Passlib |
| Rate Limiting | SlowAPI |
| Migrations | Alembic |
| Testing | pytest |
| Coverage | pytest-cov |
| Performance Testing | Grafana k6 |
| Containerization | Docker |
| API Documentation | OpenAPI / Swagger UI |

## Architecture

```text
                   Client
                     |
                     v
              FastAPI Application
                     |
          +----------+----------+
          |                     |
          v                     v
    JWT Authentication     Rate Limiting
          |                     |
          +----------+----------+
                     |
                     v
               API Endpoints
                     |
          +----------+----------+
          |          |          |
          v          v          v
       Services  Repositories  Validation
          |          |
          +-----+----+
                |
         +------+------+
         |             |
         v             v
     PostgreSQL      Redis
     Database        Cache
```

## Project Structure

```text
telecom-rest-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core.py
│   ├── models.py
│   ├── schemas.py
│   ├── repositories.py
│   ├── services.py
│   ├── security.py
│   ├── cache.py
│   └── seed.py
│
├── migrations/
│   └── versions/
│
├── tests/
│   ├── test_api.py
│   ├── test_core.py
│   ├── test_cache.py
│   └── test_seed.py
│
├── load/
│   ├── k6-plans.js
│   └── k6-debug.js
│
├── openapi/
├── postman/
│
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

## Core Features

### 1. Authentication and Authorization

- User registration.
- JWT access-token generation.
- Password hashing.
- Authenticated user profile.
- Role-based authorization.
- Active and inactive account validation.

Supported roles:

| Role | Access |
|---|---|
| Admin | Full administrative access |
| Staff | Operational access to subscribers and related resources |
| User | Access to permitted personal operations |

### 2. Prepaid Plan Management

- Create prepaid plans.
- Retrieve all active plans.
- Retrieve individual plans.
- Search plans.
- Filter by maximum price.
- Filter by minimum data allowance.
- Pagination.
- Update plans.
- Soft-delete plans.

Plan information includes price, validity, data allowance, voice minutes, SMS allowance, and description.

### 3. Subscriber Management

- Register subscribers.
- Retrieve subscriber details.
- Search and filter subscribers.
- Update subscriber information.
- Associate subscribers with plans and telecom circles.
- Close subscriber accounts.

### 4. Recharge Management

- Create recharge transactions.
- Retrieve recharge records.
- Filter recharges by subscriber.
- Validate subscriber access and eligibility.

### 5. Usage Tracking

- Record subscriber usage.
- Retrieve usage records.
- Filter usage by subscriber.

### 6. Complaint Management

- Register complaints.
- Retrieve complaints.
- Filter by status and subscriber.
- Update complaint status.
- Track complaint information and external references.

### 7. Analytics

Provides operational summary information, including:

- Total subscribers.
- Active subscribers.
- Active prepaid plans.
- Total recharges.
- Open complaints.

## API Endpoints

Base URL:

```text
http://localhost:8000
```

API version prefix:

```text
/api/v1
```

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register a user |
| POST | `/api/v1/auth/token` | Generate JWT token |
| GET | `/api/v1/auth/me` | Get authenticated user |

### Plans

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/plans` | List and filter plans |
| GET | `/api/v1/plans/{id}` | Get plan details |
| POST | `/api/v1/plans` | Create plan |
| PUT | `/api/v1/plans/{id}` | Update plan |
| DELETE | `/api/v1/plans/{id}` | Deactivate plan |

### Circles

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/circles` | List circles |
| GET | `/api/v1/circles/{id}` | Get circle details |
| POST | `/api/v1/circles` | Create circle |
| PUT | `/api/v1/circles/{id}` | Update circle |
| DELETE | `/api/v1/circles/{id}` | Delete circle |

### Subscribers

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/subscribers` | List subscribers |
| GET | `/api/v1/subscribers/{id}` | Get subscriber details |
| POST | `/api/v1/subscribers` | Create subscriber |
| PUT | `/api/v1/subscribers/{id}` | Update subscriber |
| DELETE | `/api/v1/subscribers/{id}` | Close subscriber |

### Recharges

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/recharges` | List recharges |
| POST | `/api/v1/recharges` | Create recharge |

### Usage

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/usage` | List usage records |
| POST | `/api/v1/usage` | Record usage |

### Complaints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/complaints` | List complaints |
| POST | `/api/v1/complaints` | Create complaint |
| PATCH | `/api/v1/complaints/{id}/status` | Update complaint status |

### Analytics

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/analytics/summary` | Retrieve operational analytics |

## Getting Started

### Prerequisites

Install the following:

- Python 3.12 or compatible version.
- Docker Desktop.
- Git.
- Docker Compose.

### 1. Clone the Repository

```bash
git clone https://github.com/prashanthreddy-134/telecom-prepaid-rest-api.git
```

```bash
cd telecom-prepaid-rest-api
```

### 2. Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv venv
```

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file using the example:

```powershell
Copy-Item .env.example .env
```

Configure the required environment variables:

```env
DATABASE_URL=postgresql+psycopg://telecom:telecom_dev_password@db:5432/telecom

SECRET_KEY=replace-with-a-long-random-secret

RATE_LIMIT=120/minute

REDIS_URL=redis://redis:6379/0

PLAN_CACHE_TTL_SECONDS=60
```

Use a unique, securely generated secret key. Never commit `.env` or production credentials to GitHub.

### 5. Start the Application with Docker

```powershell
docker compose up -d --build
```

Check running containers:

```powershell
docker compose ps
```

View application logs:

```powershell
docker compose logs -f api
```

### 6. Run Database Migrations

```powershell
docker compose exec api alembic upgrade head
```

Check the current migration:

```powershell
docker compose exec api alembic current
```

### 7. Access the API

Application:

```text
http://localhost:8000
```

Swagger UI:

```text
http://localhost:8000/docs
```

ReDoc:

```text
http://localhost:8000/redoc
```

Health check:

```text
http://localhost:8000/health
```

Readiness check:

```text
http://localhost:8000/ready
```

## Redis Caching

Redis is used to cache public prepaid plan listing and detail responses.

Caching features:

- Plan list caching.
- Plan detail caching.
- Filter-aware cache keys.
- Pagination-aware cache keys.
- Configurable cache expiration.
- Generation-based cache invalidation.
- Database fallback when Redis is unavailable.

### Cache Strategy

Cache keys include the cache generation and relevant request parameters.

Example:

```text
telecom:plans:v1:g17:list:<request-hash>
```

When a plan is created, updated, or deactivated, the cache generation is incremented. Old cache entries become unreachable and expire naturally.

If Redis is unavailable, the application falls back to PostgreSQL for plan retrieval.

## Database Migrations

Alembic manages database schema changes.

Create a migration:

```powershell
docker compose exec api alembic revision --autogenerate -m "describe changes"
```

Apply migrations:

```powershell
docker compose exec api alembic upgrade head
```

Check for model/schema differences:

```powershell
docker compose exec api alembic check
```

## Testing

The project uses pytest for automated testing.

Run all tests:

```powershell
python -m pytest -v
```

Run tests with coverage:

```powershell
python -m pytest --cov=app --cov-report=term-missing
```

### Verified Test Results

| Metric | Result |
|---|---:|
| Total tests passed | 166 |
| Overall code coverage | 94.35% |
| Cache module coverage | 100% |
| Models coverage | 100% |
| Core module coverage | 97% |
| Main API module coverage | 94% |
| Services coverage | 95% |

The test suite covers API behavior, authentication, authorization, database settings, Redis caching, seed operations, and service logic.

## Performance Testing with k6

The project includes Grafana k6 scripts for testing the plans endpoint.

### Test Configuration

File:

```text
load/k6-plans.js
```

Configuration:

- Executor: Constant arrival rate.
- Request rate: 200 iterations per second.
- Duration: 60 seconds.
- Preallocated virtual users: 50.
- Maximum virtual users: 300.
- p95 latency threshold: Below 300 ms.
- HTTP failure threshold: Below 1%.

### Run the Benchmark Using Docker

```powershell
docker run --rm -v "$($PWD.Path):/work" -w /work -e BASE_URL=http://host.docker.internal:8000 grafana/k6 run load/k6-plans.js
```

### Benchmark Result

```text
Total Requests:       12001
Request Rate:        200.003604/s
Average Latency:     3.63 ms
p95 Latency:         6.39 ms
Maximum Latency:     33.21 ms
Failed Requests:     0.00%
Dropped Iterations:  0
Duration:            60 seconds
```

All configured k6 thresholds passed in the local benchmark.

## Health and Infrastructure Verification

The application includes:

- `/health` for application health.
- `/ready` for database readiness.
- PostgreSQL health checks.
- Redis health checks.
- Docker restart policies.

Infrastructure can be inspected using:

```powershell
docker compose ps
```

Check Redis:

```powershell
docker compose exec redis redis-cli PING
```

Check PostgreSQL connectivity:

```powershell
docker compose exec db pg_isready -U telecom -d telecom
```

## Security Considerations

- Passwords are hashed before storage.
- JWT authentication protects restricted endpoints.
- Role-based access controls operations.
- Input and response schemas are validated.
- API rate limiting helps control excessive requests.
- Sensitive environment variables are excluded from source control.
- Database errors and unexpected application errors are handled centrally.

For production deployment, configure secure secrets, HTTPS, database credentials, access policies, backups, monitoring, and appropriate rate limits.

## Future Improvements

- CI/CD pipeline with GitHub Actions.
- Production deployment and monitoring.
- Distributed rate limiting and multi-worker validation.
- More comprehensive endpoint-level performance tests.
- Advanced analytics and reporting.
- Improved observability and structured metrics.
- Automated database backup and recovery testing.

## Author

**Prashanth Reddy S**

GitHub: https://github.com/prashanthreddy-134

Project Repository: https://github.com/prashanthreddy-134/telecom-prepaid-rest-api

---

*Built with Python, FastAPI, PostgreSQL, Redis, and Docker.*