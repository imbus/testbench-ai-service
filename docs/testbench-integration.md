---
sidebar_position: 6
title: TestBench Integration
---

# TestBench Integration

This page explains how TestBench communicates with the AI Service and how to configure the connection.

---

## Overview

TestBench triggers AI use cases by calling the AI Service's HTTP API. Unlike the Requirement Service or Defect Service, the AI Service does **not** use a proxy wrapper — TestBench connects directly via its built-in AI integration.

Authentication is handled via **session tokens**: TestBench passes the current user's session token with every request, and the AI Service validates it against the TestBench REST API.

---

## Prerequisites

- TestBench AI Service is installed and running (see [Quickstart](getting-started/quickstart.md)).
- The `tb_server_url` in the AI Service config points to the TestBench REST API.
- The `OPENAI_API_KEY` (or your provider's key) is set in the environment.
- The TestBench version supports the AI Service integration.

---

## Configuration in TestBench

Configure the AI Service URL in TestBench to point to the running service:

```
http://127.0.0.1:8010
```

If you configured HTTPS, use `https://` instead and ensure the TestBench host trusts the certificate.

---

## Authentication Flow

```
┌─────────────────┐                                               ┌──────────────────┐
│    TestBench    │                                               │ TestBench REST   │
│       UI        │                                               │      API         │
└────────┬────────┘                                               └──────────▲───────┘
         │                                                                   │
         │ 1. User triggers AI use case                                      │
         │                                                                   │
         ▼                                                                   │
┌─────────────────────────────────────────────────────────────┐              │
│ POST /api/use-case                                          │              │
│ Header: Authorization: Bearer <session_token>               │              │
└────────┬────────────────────────────────────────────────────┘              │
         │                                                                   │
         ▼                                                                   │
┌─────────────────────────────────────────────────────────────┐              │
│           AI Service (FastAPI)                              │              │
│ ┌─────────────────────────────────────────────────────────┐ │ 2. Validate  │
│ │ 1. Extract session token from header                    │ │    token     │
│ │ 2. Call TestBench REST API to verify token              ├─┼──────────────┘
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 3. Check user roles (Admin/TestManager/TestDesigner)    │ │
│ └─────────────────────────────────────────────────────────┘ │
└────────┬────────────────────────────────────────────────────┘
         │
         │ 4. Return 202 Accepted
         │    (processing in background)
         │
         ▼
┌─────────────────┐
│    TestBench    │
│   (receives     │
│   response)     │
└─────────────────┘
```

1. The user triggers an AI use case in the TestBench UI.
2. TestBench sends a POST request to the AI Service with the user's session token as the `Authorization` header.
3. The AI Service validates the token by calling the TestBench REST API.
4. If valid, the AI Service checks that the authenticated user has the required project role.
5. The request is accepted and processed in the background.

No separate username/password configuration is needed — the AI Service inherits the user's TestBench session.

---

## Role Requirements

The authenticated user must have at least one of the following TestBench roles:

- **Administrator**
- **TestManager**
- **TestDesigner**

Requests from users without sufficient permissions receive a `403 Forbidden` response.

---

## Verifying the Connection

1. Start the AI Service:
   ```bash
   testbench-ai-service start
   ```

2. Open [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs) in a browser — the Swagger UI should load.

3. Trigger an AI use case from TestBench. Check the AI Service logs for incoming requests.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Connection refused` | Service is not running or port mismatch | Start the service; verify `host` and `port` in config. |
| `401 Unauthorized` | Invalid or expired session token | Re-login to TestBench and retry. |
| `502 Bad Gateway` | AI Service cannot reach TestBench REST API | Verify `tb_server_url` in `config.toml` is correct and reachable. |
| `404 Not Found` | Use case disabled for the project | Check `enabled = true` in the use case config; check project-specific overrides. |
| `409 Conflict` | Precheck failed (e.g., all items locked) | Unlock the test structure elements in TestBench and retry. |
| LLM errors in logs | Missing or invalid API key | Verify `OPENAI_API_KEY` is set in `.env` or environment. |

---

## Network Considerations

- By default the service listens on `127.0.0.1` (loopback only). To accept connections from another machine (e.g., TestBench running on a different host), set `host = "0.0.0.0"` in `config.toml`.
- If a firewall is in place, open the configured port (default `8010`).
- For production deployments, consider enabling HTTPS — see [Configuration](configuration.md#https--tls).
