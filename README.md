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

`--target_program` accepts a bare name (`chrome.exe`, `chromium.exe`, `firefox.exe`);
it searches PATH and the usual install directories. `chromium.exe` maps to Chrome
if no real Chromium is installed.

## How it proxies

There are three cases, and the difference matters:

- **Chromium family** (chrome, chromium, msedge, brave, vivaldi, opera): uses
  `--proxy-server=socks5://...` plus `--host-resolver-rules` so DNS is resolved
  at the proxy rather than locally, which would otherwise leak your real IP.
  Launches in its own profile — without that, an already-running browser would
  just open a tab in the existing, *unproxied* process.
- **Firefox family**: writes a temp profile with `network.proxy.socks*` prefs,
  including `socks_remote_dns`.
- **Everything else**: sets `ALL_PROXY` / `HTTP_PROXY` / `HTTPS_PROXY`. This only
  works for programs that honour those variables (curl, git, requests, most CLI
  tooling). It is **not** a universal traffic intercept — a program that ignores
  the variables will connect directly. Forcing all traffic regardless of the
  program would need a driver-level redirector (WinDivert/Proxifier).

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

## Build

```
python -m PyInstaller --onefile --console --name proxy_wrapper proxy_wrapper.py
```
