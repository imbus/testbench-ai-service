---
sidebar_position: 4
title: Web Console
---
# Web Console

The TestBench AI Service ships with a browser console for inspecting a running
service. Once the service is up, open it at:

```
http://<host>:<port>/admin
```

With the default `host` and `port` that is <http://127.0.0.1:8010/admin>.

The console shows the current service status, a tail of the log file, and the
effective Service, LLM and Logging configuration.

:::info
This release is **read-only**. The console displays configuration but cannot
change it; edit `config.toml` and restart the service to apply changes. Editing
from the browser is planned for a later release.
:::

---

## Signing in

The console has no user database of its own. You sign in with the same
TestBench credentials you use for TestBench itself, and the service forwards
them to the TestBench server configured as `tb_server_url`.

That server is fixed by the service configuration and is shown on the sign-in
screen — the console cannot be pointed at a different TestBench server from the
browser.

Your TestBench password is never stored. On a successful login the service keeps
the resulting TestBench session server-side and hands the browser only an opaque
session id in an `httpOnly` cookie, plus a CSRF token the console echoes back on
every request that changes state.

A session ends after 60 minutes without activity, after 8 hours in total, or as
soon as you sign out — whichever comes first.

### Roles

The console reads your global TestBench roles at sign-in:

| Role                             | What you get                                       |
| -------------------------------- | -------------------------------------------------- |
| Global `Administrator`           | Full console; will be able to change settings once editing ships |
| Any other role                   | Read-only console                                  |

Because this release is read-only, both groups currently see the same screens.
The distinction matters from the release that introduces editing onwards.

---

## Configuration

**`[testbench-ai-service.admin_ui]`**

| Option              | Type    | Description                                                             | Default  |
| ------------------- | ------- | ----------------------------------------------------------------------- | -------- |
| `enabled`           | Boolean | Serve the console at `/admin`. When `false`, both `/admin` and the console API return `404`. | `true`   |
| `require_loopback`  | Boolean | Refuse console requests from any client that is not on this machine.    | `false`  |

**Example:**

```toml
# config.toml
[testbench-ai-service.admin_ui]
enabled = true
require_loopback = false
```

Disabling the console does not affect the agent endpoints — the service keeps
serving `/docs` and the agent API as usual.

### Security note

The console is reachable wherever the service itself is reachable. The default
`host = "127.0.0.1"` binds to loopback only, so the console stays on the
machine running the service. Changing `host` to `0.0.0.0` or a LAN address
exposes the console — and its TestBench sign-in form — to everyone who can
reach that address.

If you need a non-loopback bind for the agent API but want the console to stay
local, set:

```toml
[testbench-ai-service.admin_ui]
require_loopback = true
```

Anything that is not a loopback client then gets `403` from `/admin`, while the
agent endpoints remain reachable.

The session cookies are issued with the `Secure` flag when the service
terminates TLS itself, that is when both `ssl_cert` and `ssl_key` are set. A
reverse proxy that terminates TLS in front of a plain-HTTP service does not
change that, so keep the hop between proxy and service on a trusted network.
See [HTTPS / TLS](configuration.md#https--tls) and
[Reverse proxy](configuration.md#reverse-proxy).

---

## Troubleshooting

**`/admin` shows a page saying the console has not been built.**
The service is running from a source checkout whose frontend assets were never
built. Build them once:

```bash
cd frontend
npm ci
npm run build
```

Then restart the service. Release binaries ship with the console already built,
so this only affects development installs.

**`/admin` returns `404`.**
The console is switched off. Set `enabled = true` under
`[testbench-ai-service.admin_ui]` and restart.

**`/admin` returns `403`.**
`require_loopback = true` and the request did not come from this machine. Open
the console on the host running the service, or set `require_loopback = false`.

**Sign-in fails with a connection error.**
The service could not reach `tb_server_url`. Check that value, and — for a
TestBench server with a self-signed certificate — `tb_ssl_verify` and
`tb_ssl_ca_bundle`. See [Configuration](configuration.md#service-settings).

**The log panel is empty.**
The console tails the file named by
`[testbench-ai-service.logging.file] file_name`. If file logging is disabled or
the path points somewhere unwritable, there is nothing to show. See
[Logging](configuration.md#logging).
