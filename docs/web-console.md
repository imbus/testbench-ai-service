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

The console can change the Service, LLM provider and Logging settings. Agents,
per-project overrides and prompts are still read-only from the browser and
arrive in a later release.

:::caution
Changing configuration from the console rewrites `config.toml` on the server.
The previous contents are always kept alongside as `config.toml.bak`, and your
comments and formatting are preserved.
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
| Global `Administrator`           | Full console, including changing configuration     |
| Any other role                   | Read-only console                                  |

Editing is Administrator-only. A non-admin session sees the same screens with
the values displayed rather than as form fields, and every route that changes
something refuses a non-admin regardless of what the browser sends.

---

## Changing configuration

Edits are queued, reviewed, then written — nothing is saved as you type.

1. Change fields on the **Service**, **LLM provider** or **Logging** screen. A
   strip appears at the top of the console counting the queued changes.
2. **View diff** shows the exact unified diff that would be written, the file
   it would be written to, and whether the change needs a service restart.
3. **Apply** validates the result, writes `config.toml` atomically, and reloads
   the service in place. **Discard** throws the queued changes away.

Queued changes live in your browser, so they survive a page reload and are not
visible to anyone else. Two administrators editing at once do not clobber each
other silently: the diff is always computed against the file as it is on disk at
that moment, so the second one to apply sees the first one's changes in the
diff.

### What is written

The console edits `config.toml` in place through a comment-preserving TOML
document. Your comments, key order and formatting survive a save, and only the
keys you actually changed are touched — the console never expands the file with
every default.

Clearing a field removes its key rather than writing an empty value, so the
setting returns to its documented default.

The previous contents are kept as `config.toml.bak` next to the file. That is a
single undo step, not a history: each save overwrites it.

A configuration the service could not start with is refused before anything is
written, with the error marked against the offending field. A rejected apply
cannot leave a file the service will not boot from.

### Hot reload and restart

Most changes take effect immediately. The service re-applies logging, reloads
translations, swaps the configuration every request reads, and rebuilds its LLM
clients.

These cannot be swapped in a running process:

| Setting | Why |
| --- | --- |
| `host`, `port` | Handed to the web server when it binds its socket |
| `ssl_cert`, `ssl_key`, `ssl_ca_cert` | Same — TLS is configured at bind time |
| `trusted_proxies` | Fixed when the middleware stack is built |
| `admin_ui.enabled` | The console and its static files are mounted once, at startup |
| An agent's `endpoint_path` or `class_path` | Agent routes are registered once, at startup |

Note that `admin_ui.require_loopback` is hot-swappable — it is read per request,
unlike its sibling `admin_ui.enabled`.

Those are written to `config.toml` and then flagged: the console shows a
"restart needed" strip naming the settings involved, and the service keeps
running with its old values until you restart it. The console will not restart
the service for you — that only works reliably under a supervisor. See
[Windows service installation](windows-service-installation.md), or stop and
start the process however you normally run it.

### Logging validation

Before the console writes `config.toml`, it validates that the log file path is
usable. An unwritable path — a directory that does not exist, a path that is
actually a directory, an empty value — is refused with a field-addressed error
and nothing is written.

This check runs before any write because the service calls the same logging
setup at startup. Writing a path that fails this check would produce a
`config.toml` the service could not boot from. Therefore, when a path is
refused, the reason is that the service would reject it, not that the console
is being overly cautious.

### Raw config.toml

The **Raw config.toml** screen shows the file the current queued changes would
produce, generated by the server rather than the browser, so it is the actual
text an apply would write. It is read-only; **Copy** puts it on the clipboard.

Credential-named values (`api_key`, `password`, `token`, `secret`, `credential`,
and their hyphenated and dot-separated variants like `api-key`, `x-api-key`,
`api.key`) are displayed as `***REDACTED***`. This is display-only — the file
on disk keeps the real values, and applying changes never writes the placeholder.
Without this redaction, credentials would leak on the Raw screen and in the
preview diff.

### Apply result

When **Apply** succeeds, the response indicates whether the reload succeeded or
completed with degradation. A change can be written and the service reloaded but
with a warning — for instance the new logging configuration could not be
applied — in which case the console shows the reason directly. This is important
when the logging path itself is the problem: a reason logged to a file that
cannot be written has nowhere to go, so the reason must be shown in the console
instead.

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
