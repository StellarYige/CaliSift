"""GitHub Pages administration using the repository's existing Git credential.
Credentials are passed in memory and never printed or written to disk.
"""

import argparse
import json
import os
import subprocess
import urllib.request
import urllib.error

REPO = "StellarYige/CaliSift"


def token():
    value = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if value:
        return value
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        timeout=30,
    )
    values = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    if not values.get("password"):
        raise RuntimeError("No GitHub credential available for this repository")
    return values["password"]


def api(route, method="GET", data=None):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + route,
        method=method,
        headers={
            "Authorization": "Bearer " + token(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "CaliSift-web-build",
        },
        data=json.dumps(data).encode() if data is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            return json.load(r) if r.status != 204 else {}
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "message": json.loads(e.read()).get("message", "GitHub request failed"),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "enable", "runs"])
    args = parser.parse_args()
    if args.action == "status":
        r = api("")
        print(
            json.dumps(
                {
                    k: r.get(k)
                    for k in [
                        "full_name",
                        "private",
                        "default_branch",
                        "permissions",
                        "status",
                        "message",
                    ]
                }
            )
        )
        print(json.dumps(api("/pages")))
    elif args.action == "enable":
        r = api("/pages")
        method = "POST" if r.get("status") == 404 else "PUT"
        print(json.dumps(api("/pages", method, {"build_type": "workflow"})))
    else:
        r = api("/actions/runs?per_page=5")
        print(
            json.dumps(
                [
                    dict(
                        id=v["id"],
                        name=v["name"],
                        status=v["status"],
                        conclusion=v["conclusion"],
                        url=v["html_url"],
                        head_sha=v["head_sha"],
                    )
                    for v in r.get("workflow_runs", [])
                ]
            )
        )
