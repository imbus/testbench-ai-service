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

The console can change the Service, LLM provider and Logging settings, which
agents run and which prompt each one uses, and which of those decisions a given
TestBench project overrides. It can also edit the prompt files themselves —
their messages, variables and variants — with a lint and a sandboxed preview.

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

## Agents

The **Agents** screen lists every agent the service knows about, with a switch
for each one, its endpoint path, and how many projects override it. Expanding a
row names those projects.

The **Matrix** view is the same information as a grid of agents against
projects, which is the only place the whole override picture is visible at once.

A partial `[testbench-ai-service.agents.<key>]` block overrides only the
settings it names, so switching one agent off writes exactly one line and leaves
every other agent alone.

### Agent detail

Selecting an agent opens its own screen, with a scope switcher across the top:
**Global**, then one tab per project that overrides this agent, plus a picker
for adding an override to a project that does not have one yet. Choosing a scope
only changes what you are looking at — nothing is written until you apply.

In each scope you can set:

- whether the agent is **enabled**;
- the **prompt file**, relative to `prompts_dir/<language>/`;
- the prompt **variant**, as a list of the variants that prompt actually
  declares;
- the prompt **variables**, each rendered as the control its declaration calls
  for — a number box, a checkbox, a list of allowed values, or a text area.

The variant list and the variable types come from the prompt YAML itself, not
from `config.toml`. If the prompt file cannot be read the console says so and
leaves the variant as a free-text field, so you can still correct the path that
caused it. The same happens for a prompt file configured as an absolute path
outside `prompts_dir`: the service runs it, but the console will not read
outside that directory, so it shows the variant as free text.

Prompt **variables** in a project scope are all-or-nothing. As soon as a project
sets one variable, its `vars` table replaces the global one entirely rather than
merging with it, so any variable the project does not name falls back to the
prompt's own default and not to the global value. The screen says so when it
applies.

A variable that is set in `config.toml` but not declared by the selected variant
is still shown, flagged, so a value the prompt will ignore cannot hide in the
file.

`endpoint_path` and `class_path` are shown but not editable. Defining an agent
means shipping a Python class, which is a deployment rather than a
configuration change, and a typo in either one stops the service from starting.
Edit them in `config.toml` directly; both need a restart to take effect.

:::note
An agent cannot be removed by leaving it out of `config.toml` — every built-in
agent is always present. Set `enabled = false` instead. A disabled agent
registers no endpoint, so the effect is the same, and its prompt file and class
path are no longer checked at startup.
:::

## Projects

The **Projects** screen shows one card per project, over the union of the
projects TestBench reports and the projects `config.toml` mentions. A project
that is in your configuration but not in TestBench is flagged: usually it has
been renamed or deleted there, and its overrides are no longer doing anything.

Each card carries the project's `language` override, a three-state toggle per
agent, and **Remove all overrides**, which deletes the whole project block in a
single change — including anything else the block holds, such as an
`llm_config`.

The three states of an agent toggle are deliberate and different:

| State       | Meaning                                                      |
| ----------- | ------------------------------------------------------------ |
| Inherited   | The project says nothing; the global setting applies         |
| Off         | The project explicitly disables this agent                   |
| On          | The project explicitly enables this agent                    |

Clicking cycles through all three, so an override can always be taken back off.
The same distinction applies to every field on the agent screens: a field that
is inherited shows what it inherits and from where, and **Clear override**
returns it to inheriting.

Per-project `llm_config` is not editable here. A project that already has one
is shown read-only, and you can change it in `config.toml`. Note that **Remove
all overrides** deletes the whole project block, so an `llm_config` the project
carries goes with it — the preview diff shows exactly what would be removed.

### The project list

The project list is read from TestBench once, when you sign in, and cached for
the session — the console avoids re-using your TestBench credentials any more
than it has to. The card header shows when it was fetched; **Refresh** reads it
again.

If TestBench could not be asked, the console says so and offers a free-text
field for typing a project name by hand. The name must match the name in
TestBench exactly, including spaces and punctuation.

## Prompts

The **Prompts** screen lists every `<language>/<agent>/prompt.yaml` the
service knows about, grouped by language, with each agent's name and its
variants. A prompt that fails to parse is listed too, marked with the reason
it failed instead of its variants. This is deliberate: the tree shows a broken
prompt rather than hiding it, so an operator can see which file is broken and
why — but an unparseable file has to be repaired on disk first. The editor
cannot open it.

Any signed-in session can browse the tree and open a prompt that parses.
Editing is Administrator-only, same as the rest of the console: a non-admin
sees the same form, with every control read-only.

### Prompt detail

Selecting a prompt opens an editor for:

- the prompt's **name**, **summary** and **description**;
- its **default model** and **default variant**;
- each **variant**'s own model override, its variable declarations, and its
  Jinja messages, one per role.

A message body is edited in a Jinja-aware code editor. The **Lint** button
checks every message of the selected variant at once, on demand — it does not
check continuously as you type — and reports the line of the first error in
each. It is available to any signed-in session. **Render** evaluates the
variant's messages against its variables and the agent's own context, and is
**Administrator-only** — unlike lint, it executes the template text, so a
non-admin session sees lint errors but no Render button. Preview always runs
inside a sandboxed Jinja environment, whatever the template does.

The **context** pane that Render fills in is built server-side from the real
Jinja syntax tree of the variant's messages, not guessed in the browser, so
it always agrees with what a render will actually look up.

:::note
Renaming or removing a variant that an agent or a project still points at by
name is refused. The response names the global agents table or the project
holding the reference — not a specific agent, since you are already editing
this prompt's own agent. Repoint the referencing `prompt.variant` in
`config.toml` (globally, or on that project) to a variant that will still
exist, apply that change, and only then rename or remove the old one — a
variant name is a free string elsewhere in the configuration, so nothing else
catches this at save time.
:::

:::caution
Saving a prompt rewrites the whole `prompt.yaml` file and does **not**
preserve comments you added by hand. The prompt editor serializes with
`PyYAML` rather than a comment-preserving library, unlike the configuration
editor. Key order and non-ASCII text (German prompt text, for instance) are
kept, multi-line message text is written back as a literal block scalar, and
the `# yaml-language-server: $schema=` header is re-emitted — but a comment
is not data PyYAML round-trips, so it does not survive the first save from
the console. Keep prompt notes somewhere other than the YAML file if you rely
on them.
:::

### What saving does and does not do

Saving writes `prompt.yaml` and, for any message whose text you changed and
which is already stored in an external file (`source: "file"`), that file —
both replaced in place, with the previous contents kept as `<file>.bak`
next to it.

A message whose template file could **not** be read when the prompt was
loaded — it is missing, or it is not valid UTF-8 (an old latin-1 file, say) —
is shown with its reference and an empty body, so you can see which reference
is broken. Saving is then refused, naming that file: the editor is holding a
placeholder, not the file's text, and writing it back would leave the real
file empty. Repair the file on disk first, then reload the prompt.

Phase 4a never creates or deletes a file. A message already stored externally
can be edited but not switched to inline text, and a new message is always
inline; moving a message's text out to its own file, and forking a whole
prompt into a new variant file, are not yet available from the console.

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
