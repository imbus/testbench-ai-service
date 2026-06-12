---
sidebar_position: 7
title: TestBench Integration
---
# TestBench Integration

This page explains how TestBench communicates with the AI Service and how to configure the connection.

---

## Overview

TestBench triggers AI Agents by calling the AI Service's REST API. Unlike the Requirement Service or Defect Service, the AI Service does **not** use a proxy wrapper. TestBench connects directly via its built-in AI integration.

Authentication is handled via **JWT tokens**: TestBench passes the current user's JWT token with every request, and the AI Service validates it against the TestBench REST API.

---

## Requirements

- TestBench AI Service is installed and running (see [Quickstart](getting-started/quickstart.md)).
- The `tb_server_url` in the AI Service config points to the TestBench REST API.
- The provider API key is set in the environment (for example `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY`).
- The TestBench version supports the AI Service integration.

---

## Configuration in TestBench

Configure the AI Service URL in TestBench to point to the running service:

```
http://127.0.0.1:8010
```

If you configured HTTPS, use `https://` instead and ensure the TestBench host trusts the certificate.

---

## Authentication flow

```
┌─────────────────┐                                                ┌─────────────────┐
│    TestBench    │                                                │    TestBench    │
│       UI        │                                                │     REST API    │
└────────┬────────┘                                                └────────▲────────┘
         │                                                                  │
         │ 1. User triggers AI agent                                        │
         │                                                                  │
┌────────┴────────────────────────────────────────────────────┐             │
│ POST /test-case-set-reviews                                 │             │
│ Header: Authorization: <jwt_token>                          │             │
└────────┬────────────────────────────────────────────────────┘             │
         │                                                                  │
         │                                                                  │
┌────────▼────────────────────────────────────────────────────┐             │
│ TestBench AI Service (FastAPI)                              │             │
│ ┌─────────────────────────────────────────────────────────┐ │ 2. Validate │
│ │ - Extract JWT token from header                         │ │    token    │
│ │ - Call TestBench REST API to verify token               ├─┼─────────────┘
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 3. Check user's project role for the triggered agent    │ │
│ └─────────────────────────────────────────────────────────┘ │
└────────┬────────────────────────────────────────────────────┘
         │
         │ 4. Return 202 Accepted
         │    (processing in background)
         │
┌────────▼────────┐
│   TestBench UI  │
│    (response)   │
└─────────────────┘
```

1. The user triggers an AI agent in the TestBench UI. TestBench sends a POST request to the AI Service with the user's JWT token as the `Authorization` header.
2. The AI Service validates the token by calling the TestBench REST API.
3. If valid, the AI Service checks that the authenticated user has the required project role for the triggered agent.
4. The request is accepted and processed in the background.

No separate username/password configuration is needed. The AI Service uses the JWT token issued by TestBench.

---

## Verifying the connection

1. Start the AI Service:
   ```bash
   testbench-ai-service start
   ```
2. Open [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs) in a browser. The Swagger UI should load.
3. Trigger an AI agent from TestBench. Check the AI Service logs for incoming requests.

---

## Troubleshooting

| Symptom                | Likely Cause                                | Fix                                                                                                                      |
| ---------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Connection refused` | Service is not running or port mismatch.    | Start the service; verify `host` and `port` in config.                                                               |
| `401 Unauthorized`   | Missing or invalid JWT token.               | Re-login to TestBench and retry.                                                                                         |
| `502 Bad Gateway`    | AI Service cannot reach TestBench REST API. | Verify `tb_server_url` in `config.toml` is correct and reachable.                                                    |
| `404 Not Found`      | Agent disabled for the project.             | Check `enabled = true` in the agent config; check project-specific overrides.                                          |
| `409 Conflict`       | Precheck failed (e.g., all items locked).   | Unlock the test structure elements in TestBench and retry.                                                               |
| LLM errors in logs     | Missing or invalid API key.                 | Verify your provider key is set in `.env` or environment (for example `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY`). |

---

## Network considerations

- By default the service listens on `127.0.0.1` (loopback only). To accept connections from another machine (e.g., TestBench running on a different host), set `host = "0.0.0.0"` in `config.toml`.
- If a firewall is in place, open the configured port (default `8010`).
- For production deployments, consider enabling HTTPS — see [Configuration](configuration.md#https--tls).
