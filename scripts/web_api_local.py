"""Run the web Lambda on localhost, against the REAL deployed runtime.

    python scripts/web_api_local.py        # http://127.0.0.1:8787
    cd web && npm run dev                  # vite proxies /api here

The same handler the Lambda runs, fed the same Function URL event shape, so
what works here is what deploys. It calls AgentCore with your local AWS
credentials (AWS_PROFILE=panchayat by default); the deployed Lambda has none
and uses its role instead.

After `npm run build` it serves web/dist as well, so http://127.0.0.1:8787 is
the production page end to end.

Owner: Ali (platform).
"""
from __future__ import annotations

import base64
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PANCHAYAT_WEB_PORT", "8787"))


def _runtime_arn_from_toolkit() -> str:
    """What `agentcore launch` recorded it deployed. The file is gitignored,
    so the ARN is read from it rather than copied into a tracked one."""
    cfg = ROOT / ".bedrock_agentcore.yaml"
    if not cfg.is_file():
        return ""
    import yaml

    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    agent = (data.get("agents") or {}).get(data.get("default_agent") or "") or {}
    return str((agent.get("bedrock_agentcore") or {}).get("agent_arn") or "")


def main() -> None:
    os.environ.setdefault("PANCHAYAT_SITE_DIR", str(ROOT / "web" / "dist"))
    os.environ.setdefault("AWS_PROFILE", "panchayat")
    if not os.environ.get("PANCHAYAT_RUNTIME_ARN"):
        os.environ["PANCHAYAT_RUNTIME_ARN"] = _runtime_arn_from_toolkit()

    sys.path.insert(0, str(ROOT))
    from handlers import web_api

    class Door(BaseHTTPRequestHandler):
        def _run(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b""
            path, _, query = self.path.partition("?")
            out = web_api.handler({
                "rawPath": path,
                "rawQueryString": query,
                "body": base64.b64encode(raw).decode("ascii"),
                "isBase64Encoded": True,
                "requestContext": {"http": {"method": self.command}},
            })
            body = out.get("body") or ""
            data = base64.b64decode(body) if out.get("isBase64Encoded") else body.encode()
            self.send_response(out["statusCode"])
            for key, value in (out.get("headers") or {}).items():
                self.send_header(key, value)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_HEAD = _run

    arn = os.environ["PANCHAYAT_RUNTIME_ARN"] or "(unset -- /api will answer 503)"
    print("runtime  " + arn)
    print("site     " + os.environ["PANCHAYAT_SITE_DIR"])
    print("serving  http://127.0.0.1:" + str(PORT))
    ThreadingHTTPServer(("127.0.0.1", PORT), Door).serve_forever()


if __name__ == "__main__":
    main()
