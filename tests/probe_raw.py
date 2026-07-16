import socket, ssl
try:
    s = socket.create_connection(("api.ipify.org", 443), timeout=25)
    s = ssl.create_default_context().wrap_socket(s, server_hostname="api.ipify.org")
    s.send(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
    data = b""
    while True:
        b_ = s.recv(4096)
        if not b_: break
        data += b_
    print("RAWSOCKET_SAW:" + data.decode(errors="replace").split("\r\n\r\n")[-1].strip())
except Exception as e:
    print("RAWSOCKET_ERR:" + type(e).__name__ + ":" + str(e)[:90])
