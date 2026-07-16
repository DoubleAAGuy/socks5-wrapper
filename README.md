# proxy_wrapper

Launch a program with a SOCKS5 proxy wrapped around it.

```
proxy_wrapper.exe --proxy=127.0.0.1:1080 --target_program=chromium.exe
```

## Options

| Flag | Meaning |
| --- | --- |
| `--proxy=HOST:PORT` | SOCKS5 proxy. `user:pass@host:port` for auth. |
| `--target_program=PROG` | Program to launch — bare name or full path. |
| `--args="..."` | Arguments for the program. |
| `--` | Everything after this is passed to the program. |
| `--wait` | Wait for the program to exit (needed to see its console output). |
| `--keep-profile` | Reuse a persistent browser profile instead of a temp one. |
| `--force` | Launch even if the program can't use SOCKS (it will connect directly). |

`--target_program` accepts a bare name (`chrome.exe`, `chromium.exe`, `firefox.exe`);
it searches PATH and the usual install directories. `chromium.exe` maps to Chrome
if no real Chromium is installed.

## How it proxies

There are three cases, and the difference matters a great deal:

- **Chromium family** (chrome, chromium, msedge, brave, vivaldi, opera): uses
  `--proxy-server=socks5://...` plus `--host-resolver-rules` so DNS is resolved
  at the proxy rather than locally, which would otherwise leak your real IP.
  Launches in its own profile — without that, an already-running browser would
  just open a tab in the existing, *unproxied* process.
- **Firefox family**: writes a temp profile with `network.proxy.socks*` prefs,
  including `socks_remote_dns`.
- **Everything else**: sets `ALL_PROXY` / `HTTP_PROXY` / `HTTPS_PROXY`.

**The third case is opt-in on the program's side, and most Windows software
does not opt in.** This is not a universal traffic intercept. A program that
ignores those variables connects directly and exposes your real IP, and nothing
about the launch looks wrong when it happens.

Because of that, programs measured to be incapable of SOCKS are **refused** by
default rather than launched with a false sense of safety. `--force` overrides
this and launches them unproxied, with a warning.

## What actually gets proxied

Measured against a live SOCKS5 proxy, comparing each program's egress IP against
the real one:

| Program | Result |
| --- | --- |
| Chromium / Chrome / Edge | proxied (native flags, remote DNS) |
| curl | proxied |
| git | proxied (libcurl honours `ALL_PROXY`) |
| `cmd.exe` → `curl` (child) | proxied |
| `cmd` → `cmd` → `curl` (grandchild) | proxied |
| Windows PowerShell | **cannot be proxied** — refused |
| Node.js | **cannot be proxied** — refused |
| Python `urllib` | fails — no SOCKS support in stdlib |

Verified by negative control: with a dead proxy port, curl and git **fail**
(rc=7 / rc=128) rather than silently falling back to a direct connection.

### Child processes

Child processes inherit the environment, so an exe spawned by the target is
covered on the same terms as the target itself — verified three levels deep
(`cmd` → `cmd` → `curl`). The same caveat applies: inheriting the variables only
helps if the child honours them. Browsers also get the env vars, so helper exes
they spawn are covered as far as env vars can reach.

Genuinely universal wrapping — forcing *every* program regardless of
cooperation — requires socket-level interception (DLL injection hooking
`connect`/`WSAConnect`, or a WinDivert driver redirect). That is a different and
much larger tool; this one does not pretend to do it.

## Verifying it works

Check your real IP first, then compare it against what the wrapped program sees:

```
curl https://api.ipify.org

proxy_wrapper.exe --proxy=127.0.0.1:1080 --target_program=chromium.exe --wait ^
  --args="--headless=new --dump-dom https://api.ipify.org"
```

The second command should report a different address. Tested against a SOCKS5
proxy on `127.0.0.1:1080` with both Chrome and curl; both reported the proxy's
exit IP rather than the local one.

## Note on PowerShell

PowerShell 5.1 mangles some native arguments. If `--` gives you trouble, use the
quoted `--args` form:

```powershell
.\proxy_wrapper.exe --proxy=127.0.0.1:1080 --target_program=chrome.exe --args="https://api.ipify.org"
```

## Antivirus

The exe is PyInstaller-built and unsigned, and Windows Defender flags it as
`Trojan:Win32/Bearfoos.A!ml` — a machine-learning heuristic that fires on
PyInstaller's self-extracting stub. It is a false positive, but a real
inconvenience: Defender quarantined a build of this tool during development.

Building with `--noupx` (as below) reduces it. If Defender takes the exe, either
restore it from Protection History or run from source instead — the script has
no dependencies beyond Python. Fixing this properly needs a code-signing
certificate.

## Build

```
python -m PyInstaller --onefile --console --noupx --name proxy_wrapper proxy_wrapper.py
```
