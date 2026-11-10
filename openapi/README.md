# OpenAPI Documentation

This project uses FastAPI to generate its OpenAPI specification automatically from the registered API routes, request schemas, response models, and endpoint metadata.

## Available Documentation

Start the FastAPI application and access:

| Resource | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |

## Exploring the API

The Swagger UI provides an interactive interface to:

- Browse available API endpoints.
- Inspect HTTP methods and request parameters.
- Review request and response schemas.
- Execute API requests.
- Test authenticated endpoints using JWT bearer tokens.

## OpenAPI Specification

The OpenAPI JSON document is generated dynamically by FastAPI when the application runs.

For the latest API definition, access:

`http://localhost:8000/openapi.json`

The specification reflects the routes and schemas registered in the running application.