"""proxy_wrapper - launch a program with a SOCKS5 proxy wrapped around it.

Usage:
    proxy_wrapper.exe --proxy=127.0.0.1:1080 --target_program=chrome.exe
    proxy_wrapper.exe --proxy=user:pass@host:1080 --target_program=firefox.exe -- https://example.com
"""

import os
import shutil
import subprocess
import sys
import tempfile

VERSION = "1.0"

# Browsers we can proxy natively, keyed by the stem of the executable name.
CHROMIUM_STEMS = {"chrome", "chromium", "msedge", "brave", "vivaldi", "opera", "thorium"}
FIREFOX_STEMS = {"firefox", "librewolf", "waterfox", "palemoon", "tor"}

# Where browsers commonly live, used to resolve a bare name like "chrome.exe".
KNOWN_PATHS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "msedge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
}


class Fail(Exception):
    pass


def log(msg):
    sys.stderr.write("[proxy_wrapper] %s\n" % msg)


def usage():
    return (
        "proxy_wrapper %s - run a program behind a SOCKS5 proxy\n\n"
        "  --proxy=HOST:PORT            SOCKS5 proxy (user:pass@host:port for auth)\n"
        "  --target_program=PROG        program to launch (name or full path)\n"
        "  --args=\"...\"                 arguments to pass to the program\n"
        "  --keep-profile               reuse a persistent browser profile\n"
        "  --wait                       wait for the program to exit\n"
        "  --                           everything after this goes to the program\n\n"
        "Example:\n"
        "  proxy_wrapper.exe --proxy=127.0.0.1:1080 --target_program=chrome.exe\n"
        % VERSION
    )


def parse_proxy(raw):
    """Split HOST:PORT or user:pass@HOST:PORT into its parts."""
    value = raw
    for prefix in ("socks5h://", "socks5://", "socks://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break

    user = password = None
    if "@" in value:
        creds, value = value.rsplit("@", 1)
        if ":" not in creds:
            raise Fail("proxy credentials must be user:pass, got %r" % creds)
        user, password = creds.split(":", 1)

    if ":" not in value:
        raise Fail("proxy must be HOST:PORT, got %r" % raw)
    host, port = value.rsplit(":", 1)
    if not host:
        raise Fail("proxy host is empty in %r" % raw)
    try:
        port = int(port)
    except ValueError:
        raise Fail("proxy port %r is not a number" % port)
    if not 1 <= port <= 65535:
        raise Fail("proxy port %d out of range" % port)
    return host, port, user, password


def parse_args(argv):
    opts = {
        "proxy": None,
        "target": None,
        "extra": [],
        "keep_profile": False,
        "wait": False,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            opts["extra"].extend(argv[i + 1:])
            break
        elif a.startswith("--proxy="):
            opts["proxy"] = a.split("=", 1)[1]
        elif a == "--proxy":
            i += 1
            opts["proxy"] = argv[i] if i < len(argv) else None
        elif a.startswith("--target_program=") or a.startswith("--target-program="):
            opts["target"] = a.split("=", 1)[1]
        elif a in ("--target_program", "--target-program"):
            i += 1
            opts["target"] = argv[i] if i < len(argv) else None
        elif a.startswith("--args="):
            opts["extra"].extend(split_args(a.split("=", 1)[1]))
        elif a == "--keep-profile":
            opts["keep_profile"] = True
        elif a == "--wait":
            opts["wait"] = True
        elif a in ("-h", "--help"):
            sys.stdout.write(usage())
            sys.exit(0)
        elif a == "--version":
            sys.stdout.write("proxy_wrapper %s\n" % VERSION)
            sys.exit(0)
        else:
            raise Fail("unknown option %r (see --help)" % a)
        i += 1

    if not opts["proxy"]:
        raise Fail("--proxy is required (see --help)")
    if not opts["target"]:
        raise Fail("--target_program is required (see --help)")
    return opts


def split_args(s):
    try:
        import shlex
        return shlex.split(s, posix=False)
    except Exception:
        return s.split()


def resolve_program(target):
    """Turn 'chrome.exe' into a real path, searching PATH and known install dirs."""
    if os.path.sep in target or (len(target) > 1 and target[1] == ":"):
        if os.path.isfile(target):
            return os.path.abspath(target)
        raise Fail("target program not found: %s" % target)

    found = shutil.which(target)
    if found:
        return os.path.abspath(found)

    stem = os.path.splitext(os.path.basename(target))[0].lower()
    # "chromium" is not a real install dir on Windows; Chrome is the usual stand-in.
    for key in ([stem] + (["chrome"] if stem == "chromium" else [])):
        for path in KNOWN_PATHS.get(key, []):
            if os.path.isfile(path):
                return path
    raise Fail(
        "could not find %r on PATH or in the usual install locations.\n"
        "            Pass a full path instead, e.g. "
        "--target_program=\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\""
        % target
    )


def proxy_env(host, port, user, password):
    """Env vars honoured by curl, git, python-requests and most CLI tooling."""
    if user:
        url = "socks5h://%s:%s@%s:%d" % (user, password, host, port)
    else:
        url = "socks5h://%s:%d" % (host, port)
    env = os.environ.copy()
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                 "HTTPS_PROXY", "https_proxy"):
        env[name] = url
    env["NO_PROXY"] = env["no_proxy"] = "localhost,127.0.0.1,::1"
    return env


def profile_dir(stem, keep):
    if keep:
        path = os.path.join(tempfile.gettempdir(), "proxy_wrapper_%s_profile" % stem)
        os.makedirs(path, exist_ok=True)
        return path, False
    return tempfile.mkdtemp(prefix="proxy_wrapper_%s_" % stem), True


def build_chromium(exe, host, port, user, extra, keep):
    stem = os.path.splitext(os.path.basename(exe))[0].lower()
    profile, temporary = profile_dir(stem, keep)
    if user:
        log("note: Chromium ignores SOCKS5 username/password; proxy must allow this IP.")
    cmd = [
        exe,
        "--proxy-server=socks5://%s:%d" % (host, port),
        # Without this Chromium still resolves DNS locally, leaking the real IP.
        "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE %s" % host,
        # A dedicated profile is required: an already-running browser would
        # otherwise just open a tab in the existing, unproxied process.
        "--user-data-dir=%s" % profile,
        "--no-first-run",
        "--no-default-browser-check",
    ]
    cmd.extend(extra)
    return cmd, (profile if temporary else None)


def build_firefox(exe, host, port, extra, keep):
    stem = os.path.splitext(os.path.basename(exe))[0].lower()
    profile, temporary = profile_dir(stem, keep)
    prefs = "\n".join([
        'user_pref("network.proxy.type", 1);',
        'user_pref("network.proxy.socks", "%s");' % host,
        'user_pref("network.proxy.socks_port", %d);' % port,
        'user_pref("network.proxy.socks_version", 5);',
        # Resolve DNS at the proxy, not locally.
        'user_pref("network.proxy.socks_remote_dns", true);',
        'user_pref("browser.shell.checkDefaultBrowser", false);',
        'user_pref("browser.aboutwelcome.enabled", false);',
        "",
    ])
    with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as fh:
        fh.write(prefs)
    cmd = [exe, "-profile", profile, "-no-remote"]
    cmd.extend(extra)
    return cmd, (profile if temporary else None)


def std_handles():
    """Hand our stdout/stderr to the child explicitly.

    GUI-subsystem programs (chrome.exe) have no console to fall back on, so
    unless the handles are passed explicitly their output goes nowhere. This is
    what makes `--dump-dom` and friends usable through the wrapper.
    """
    kwargs = {}
    for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            stream.fileno()
        except Exception:
            continue  # no real handle (pythonw / windowed build); let it inherit
        kwargs[name] = stream
    return kwargs


def main(argv):
    try:
        opts = parse_args(argv)
        host, port, user, password = parse_proxy(opts["proxy"])
        exe = resolve_program(opts["target"])
    except Fail as e:
        log("error: %s" % e)
        return 2

    stem = os.path.splitext(os.path.basename(exe))[0].lower()
    cleanup = None

    if stem in CHROMIUM_STEMS:
        mode = "chromium native SOCKS5"
        cmd, cleanup = build_chromium(exe, host, port, user, opts["extra"],
                                      opts["keep_profile"])
        env = os.environ.copy()
    elif stem in FIREFOX_STEMS:
        mode = "firefox profile SOCKS5"
        cmd, cleanup = build_firefox(exe, host, port, opts["extra"],
                                     opts["keep_profile"])
        env = os.environ.copy()
    else:
        mode = "proxy environment variables"
        cmd = [exe] + opts["extra"]
        env = proxy_env(host, port, user, password)
        log("note: %s is not a known browser. Applying proxy env vars, which only"
            % os.path.basename(exe))
        log("      work for programs that honour them (curl, git, requests, ...).")

    log("proxy   : socks5://%s:%d" % (host, port))
    log("program : %s" % exe)
    log("mode    : %s" % mode)

    try:
        proc = subprocess.Popen(cmd, env=env, **std_handles())
    except OSError as e:
        log("error: failed to launch %s: %s" % (exe, e))
        return 2

    log("launched pid %d" % proc.pid)

    if not opts["wait"]:
        # Detaching would strand the temp profile on disk, so keep it either way.
        if cleanup:
            log("temp profile: %s" % cleanup)
        return 0

    try:
        code = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        code = 130
    if cleanup:
        shutil.rmtree(cleanup, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
