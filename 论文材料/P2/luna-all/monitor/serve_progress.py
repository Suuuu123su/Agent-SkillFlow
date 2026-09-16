"""Serve only fixed dashboard assets and the validated public status, on loopback.
This process never starts, resumes, judges, or stops an experiment.
"""
from __future__ import annotations
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from progress_writer import project_snapshot

ASSETS = Path(__file__).resolve().parent
MAX_STATUS_BYTES = 512 * 1024
ROUTES = {'/':('index.html','text/html; charset=utf-8'),
          '/index.html':('index.html','text/html; charset=utf-8'),
          '/style.css':('style.css','text/css; charset=utf-8'),
          '/app.js':('app.js','application/javascript; charset=utf-8')}


def create_server(status_file: Path, port: int = 8765) -> ThreadingHTTPServer:
    status_file = Path(status_file).resolve()
    class Handler(BaseHTTPRequestHandler):
        server_version = 'SkillFlowProgress/1'
        sys_version = ''
        def log_message(self, fmt: str, *args: object) -> None:
            pass  # Do not log user-controlled paths or request content.
        def _send(self, code: int, payload: bytes, mime: str) -> None:
            self.send_response(code)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command!='HEAD':
                try: self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError): pass
        def do_GET(self) -> None:
            actual = self.server.server_address[1]
            if self.headers.get('Host') not in {f'127.0.0.1:{actual}',f'localhost:{actual}'}:
                self._send(403,b'Host not allowed','text/plain; charset=utf-8'); return
            route = urlsplit(self.path).path
            if route in ROUTES:
                filename,mime=ROUTES[route]
                self._send(200,(ASSETS/filename).read_bytes(),mime);return
            if route!='/status.json':
                self._send(404,b'Not found','text/plain; charset=utf-8');return
            try:
                if not status_file.exists():
                    data=project_snapshot({'state':'NOT_CONNECTED','phase':'BINDING'})
                else:
                    with status_file.open('rb') as stream:
                        raw=stream.read(MAX_STATUS_BYTES+1)
                    if len(raw)>MAX_STATUS_BYTES: raise ValueError('oversized status')
                    data=project_snapshot(json.loads(raw.decode('utf-8')))
                self._send(200,json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8'),
                           'application/json; charset=utf-8')
            except (OSError,ValueError,TypeError,KeyError,UnicodeError):
                # Preserve previous valid view in the browser; never replace with fake zeros.
                self._send(503,b'{"error_code":"PUBLIC_STATUS_UNAVAILABLE"}',
                           'application/json; charset=utf-8')
        def do_HEAD(self) -> None: self.do_GET()
        def do_POST(self) -> None: self._send(405,b'Read-only monitor','text/plain; charset=utf-8')
        def do_PUT(self) -> None: self.do_POST()
        def do_DELETE(self) -> None: self.do_POST()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--status-file',required=True,type=Path)
    p.add_argument('--port',default=8765,type=int)
    args=p.parse_args()
    if not 0<=args.port<=65535: p.error('port out of range')
    try: server=create_server(args.status_file,args.port)
    except OSError:
        print('Port unavailable. Choose another port; do not terminate unrelated processes.',file=sys.stderr)
        return 2
    print(f'Read-only monitor: http://127.0.0.1:{server.server_address[1]}/',flush=True)
    print('Waiting for real runner status. This server does not run models.',flush=True)
    try: server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0

if __name__=='__main__': raise SystemExit(main())
