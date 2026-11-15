"""Servidor web del portal cautivo + app Kangaroo Path.

Cualquier peticion a un dominio que no sea el Arduino (por ejemplo las comprobaciones
de conexion de Android, iOS o Windows) se redirige a http://192.168.4.1/, lo que hace
que el movil abra la web automaticamente.

En el portatil, para probar:
    python server.py --port 8000 --dev      ->  http://localhost:8000
"""
import os
import sys
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import load  # noqa: E402
from app.service import Service  # noqa: E402
from app.web import make_handler  # noqa: E402

WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, help="override config.json port (default 80)")
    ap.add_argument("--dev", action="store_true", help="accept any Host header (no captive redirects)")
    ap.add_argument("--reset-demo", action="store_true",
                    help="move the database to data/backup/ and exit: the next start recreates the example classroom")
    a = ap.parse_args()
    if a.port:
        os.environ["EDU_PORT"] = str(a.port)
    if a.dev:
        os.environ["EDU_DEV"] = "1"
    cfg = load(os.environ.get("EDU_CONFIG"))
    if a.reset_demo:
        from app.service import reset_database
        moved = reset_database(cfg["data_dir"])
        print("database moved to " + (moved or "(there was none)") + "; restart the portal to recreate the demo",
              flush=True)
        return
    svc = Service(cfg)
    server = ThreadingHTTPServer(("0.0.0.0", cfg["port"]), make_handler(svc, WWW))
    server.daemon_threads = True
    print(f"Kangaroo Path en el puerto {cfg['port']} ({len(svc.index)} problemas, embedder={svc.embedder.name})",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
