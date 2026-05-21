#!/usr/bin/env python3
"""
Minimal CONNECT-logging HTTPS proxy. Logs the destination host:port for every
outgoing request, then forwards bytes bidirectionally without TLS interception.

For HTTPS, clients send `CONNECT host:port HTTP/1.1` first — that's exactly the
data we want to capture for observability. We just pipe the encrypted bytes
through; we don't decrypt anything.

For plain HTTP (rare for our use case), we log the Host header and forward the
full request.

Output: one JSON line per connection to LOG_PATH.
"""
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

LOG_PATH = Path(os.environ.get("PROXY_LOG", "/logs/agent/network/egress.jsonl"))
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "8080"))


def log_event(**fields):
    fields["ts"] = time.time()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(fields) + "\n")


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle_connect(client_r, client_w, host, port):
    log_event(method="CONNECT", host=host, port=port)
    try:
        srv_r, srv_w = await asyncio.open_connection(host, port)
    except Exception as e:
        log_event(method="CONNECT", host=host, port=port, error=str(e))
        client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await client_w.drain()
        client_w.close()
        return
    client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await client_w.drain()
    await asyncio.gather(pipe(client_r, srv_w), pipe(srv_r, client_w))


async def handle_http(client_r, client_w, method, url, version, initial_headers, host_header):
    # very basic HTTP forwarding for plain-text requests
    if "://" in url:
        # absolute URI form (proxy style)
        _, _, rest = url.partition("://")
        host_part, _, path = rest.partition("/")
        host_header = host_part
        url = "/" + path
    host, _, port_s = host_header.partition(":")
    port = int(port_s) if port_s else 80
    log_event(method=method, host=host, port=port, path=url)
    try:
        srv_r, srv_w = await asyncio.open_connection(host, port)
    except Exception as e:
        log_event(method=method, host=host, port=port, error=str(e))
        client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await client_w.drain()
        client_w.close()
        return
    srv_w.write(f"{method} {url} {version}\r\n".encode())
    srv_w.write(initial_headers)
    await srv_w.drain()
    await asyncio.gather(pipe(client_r, srv_w), pipe(srv_r, client_w))


async def handle_client(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter):
    try:
        request_line = await client_r.readline()
        if not request_line:
            client_w.close()
            return
        try:
            parts = request_line.decode("latin-1").rstrip("\r\n").split(" ", 2)
            method, url, version = parts[0], parts[1], parts[2] if len(parts) > 2 else "HTTP/1.1"
        except Exception:
            client_w.close()
            return

        headers_raw = b""
        host_header = ""
        while True:
            line = await client_r.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            headers_raw += line
            if line.lower().startswith(b"host:"):
                host_header = line.decode("latin-1").split(":", 1)[1].strip()
        headers_raw += b"\r\n"

        if method.upper() == "CONNECT":
            host, _, port_s = url.partition(":")
            port = int(port_s) if port_s else 443
            await handle_connect(client_r, client_w, host, port)
        else:
            await handle_http(client_r, client_w, method, url, version, headers_raw, host_header)
    except Exception as e:
        log_event(method="ERROR", error=str(e))
        try:
            client_w.close()
        except Exception:
            pass


async def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_event(method="STARTUP", listen=f"{LISTEN_HOST}:{LISTEN_PORT}", pid=os.getpid())
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
