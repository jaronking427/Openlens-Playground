# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests>=2.31",
#     "python-dotenv>=1.0",
# ]
# ///
"""OpenLens API playground.

Each API call is its own function and its own subcommand:

    python main.py projects
    python main.py run-start --project <id>
    python main.py visibility

Every response is saved to output/<command>_<timestamp>.json.
IDs that rarely change (projects, topics, brands, runs) are cached in cache.json,
so you can look them up without paying for another API call. When --project is
omitted, the last project you used is taken from the cache.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENLENS_API_KEY")
BASE_URL = os.getenv("OPENLENS_BASE_URL", "https://openlens.com/api").rstrip("/")

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
CACHE_FILE = ROOT / "cache.json"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def request(method, path, params=None, body=None, raw=False, allow=()):
    """Send a request to the OpenLens API and return the parsed JSON (or bytes if raw).

    Error statuses listed in `allow` return their JSON body instead of exiting.
    """
    if not API_KEY:
        sys.exit("OPENLENS_API_KEY is not set. Add it to your .env file.")

    # Drop unset optional parameters so we don't send "None" to the API.
    if params:
        params = {k: v for k, v in params.items() if v is not None}

    resp = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        params=params,
        json=body,
        timeout=120,
    )

    if not resp.ok and resp.status_code not in allow:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        print(f"Error {resp.status_code} from {method} {path}:")
        print(json.dumps(detail, indent=2) if isinstance(detail, (dict, list)) else detail)
        sys.exit(1)

    if raw:
        return resp.content
    return resp.json() if resp.content else {}


def save_output(name, data):
    """Save a response to output/<name>_<timestamp>.json and return the path."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{name}_{stamp}.json"
    path.write_text(json.dumps(data, indent=2))
    print(f"\nSaved to {path.relative_to(ROOT)}")
    return path


def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {"lastProjectId": None, "projects": {}, "runs": {}, "topics": {}, "brands": {}, "prompts": {}}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def remember(section, key, value):
    """Store a value in cache.json under cache[section][key]."""
    cache = load_cache()
    cache.setdefault(section, {})[key] = value
    save_cache(cache)


def resolve_project(project_id):
    """Use the given project ID, or fall back to the last one in the cache."""
    cache = load_cache()
    project_id = project_id or cache.get("lastProjectId")
    if not project_id:
        sys.exit("No project ID given and none cached. Run `python main.py projects` first, "
                 "or pass --project <id>.")
    cache["lastProjectId"] = project_id
    save_cache(cache)
    return project_id


def show(data):
    print(json.dumps(data, indent=2))


def ask(label, current=None):
    """Prompt for a value. Blank keeps the current value (returns None)."""
    hint = f" [{current}]" if current not in (None, "") else ""
    value = input(f"{label}{hint}: ").strip()
    return value or None


def confirm(question):
    return input(f"{question} [y/N] ").strip().lower() == "y"


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #

def start_run(project_id, platforms=None):
    """POST /prompts/run — start (or resume) a prompt run. This costs money."""
    body = {"projectId": project_id}
    if platforms:
        body["platforms"] = platforms
    data = request("POST", "/prompts/run", body=body)
    remember("runs", data["runId"], {
        "projectId": project_id,
        "status": data.get("status"),
        "startedAt": datetime.now().isoformat(timespec="seconds"),
        "platforms": platforms,
    })
    print(f"Run {data['runId']} is {data['status']}" + (" (resumed)" if data.get("resumed") else ""))
    return data


def cancel_run(project_id):
    """DELETE /prompts/run — cancel the running run for a project."""
    data = request("DELETE", "/prompts/run", body={"projectId": project_id})
    show(data)
    return data


def run_status(project_id, run_id=None):
    """GET /prompts/status — poll the status of a run."""
    data = request("GET", "/prompts/status", params={"projectId": project_id, "runId": run_id})
    if data.get("runId"):
        remember("runs", data["runId"], {
            "projectId": project_id,
            "status": data.get("status"),
            "startedAt": data.get("startedAt"),
            "completedAt": data.get("completedAt"),
        })
    print(f"Run {data.get('runId')}: {data.get('status')} "
          f"({data.get('completedTasks')}/{data.get('totalTasks')} tasks, "
          f"{data.get('failedTasks')} failed)")
    return data


def list_runs(project_id, limit=20, status=None):
    """GET /prompts/runs — list a project's prompt run history."""
    data = request("GET", "/prompts/runs",
                   params={"projectId": project_id, "limit": limit, "status": status})
    for run in data.get("runs", []):
        remember("runs", run["id"], {
            "projectId": project_id,
            "status": run.get("status"),
            "startedAt": run.get("startedAt"),
            "completedAt": run.get("completedAt"),
            "platforms": run.get("platforms"),
        })
        print(f"#{run.get('ordinal')}  {run['id']}  {run.get('status'):<11} "
              f"{run.get('startedAt')}  {', '.join(run.get('platforms') or [])}")
    return data


def run_results(project_id, run_id=None, platform=None, topic_id=None, limit=None):
    """GET /prompts/results — raw platform responses, with mentions and citations."""
    data = request("GET", "/prompts/results", params={
        "projectId": project_id, "runId": run_id, "platform": platform,
        "topicId": topic_id, "limit": limit,
    })
    for item in data:
        print("=" * 80)
        print(f"[{item.get('llmPlatform')}] {item.get('promptUsed')}")
        print("-" * 80)
        print(item.get("rawResponse"))
        print(f"\n{len(item.get('citations') or [])} citations, "
              f"{len(item.get('mentions') or [])} mentions")
    return data


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def visibility(project_id, run_id=None, topic_id=None):
    """GET /visibility — visibility scores for the latest or selected run."""
    data = request("GET", "/visibility",
                   params={"projectId": project_id, "runId": run_id, "topicId": topic_id})
    show(data)
    return data


def visibility_trends(project_id, brand_id=None, days=None, compare=None):
    """GET /visibility/trends — time-series visibility for a brand or all competitors."""
    data = request("GET", "/visibility/trends", params={
        "projectId": project_id, "brandId": brand_id, "days": days, "compare": compare,
    })
    show(data)
    return data


def engine_insights(project_id, run_id=None):
    """GET /insights/engines — per-platform source behavior patterns."""
    data = request("GET", "/insights/engines", params={"projectId": project_id, "runId": run_id})
    show(data)
    return data


def topic_insight(project_id, topic_id, run_id=None):
    """GET /insights/topic — AI-generated insight paragraph for one topic."""
    data = request("GET", "/insights/topic",
                   params={"projectId": project_id, "topicId": topic_id, "runId": run_id})
    show(data)
    return data


# --------------------------------------------------------------------------- #
# Citations
# --------------------------------------------------------------------------- #

def brand_mentions(project_id, run_id=None, limit=None):
    """GET /brand-mentions-summary — top topics where your brand was mentioned, with cited URLs."""
    data = request("GET", "/brand-mentions-summary",
                   params={"projectId": project_id, "runId": run_id, "limit": limit})
    for topic in data:
        print(f"{topic.get('topicName')}: {topic.get('count')} mentions, "
              f"best position {topic.get('bestPosition')}, {topic.get('dominantSentiment')}")
        for url in topic.get("urls") or []:
            print(f"    {url.get('url')}")
    return data


def sources(project_id, run_id=None, platform=None, limit=None):
    """GET /sources — top cited domains for the latest or selected run."""
    data = request("GET", "/sources", params={
        "projectId": project_id, "runId": run_id, "platform": platform, "limit": limit,
    })
    for src in data:
        print(f"{src.get('count'):>4}  {src.get('domain')}  ({', '.join(src.get('platforms') or [])})")
    return data


# --------------------------------------------------------------------------- #
# Deliverables
# --------------------------------------------------------------------------- #

def download_report(project_id, run_id):
    """GET /reports/visibility — download a client-ready PDF report."""
    pdf = request("GET", "/reports/visibility",
                  params={"projectId": project_id, "runId": run_id}, raw=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"report_{run_id}.pdf"
    path.write_bytes(pdf)
    print(f"Saved PDF to {path.relative_to(ROOT)}")
    return {"pdf": str(path)}


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #

def list_projects():
    """GET /projects — list your projects."""
    data = request("GET", "/projects")
    cache = load_cache()
    for p in data:
        cache["projects"][p["id"]] = {
            "name": p.get("name"),
            "url": p.get("url"),
            "location": p.get("location"),
            "languages": p.get("languages"),
            "ownBrandName": p.get("ownBrandName"),
            "activePlatforms": p.get("activePlatforms"),
            "lastRunAt": p.get("lastRunAt"),
        }
        print(f"{p['id']}  {p.get('name')}  ({p.get('url')})  last run: {p.get('lastRunAt')}")
    if len(data) == 1 and not cache.get("lastProjectId"):
        cache["lastProjectId"] = data[0]["id"]
    save_cache(cache)
    return data


def project_platforms(project_id):
    """GET /projects/{id}/platforms — active platforms and your entitlement."""
    data = request("GET", f"/projects/{project_id}/platforms")
    show(data)
    return data


def list_brands(project_id):
    """GET /brands — your own brand and competitors."""
    data = request("GET", "/brands", params={"projectId": project_id})
    items = data if isinstance(data, list) else data.get("brands", [])
    for b in items:
        remember("brands", b["id"], {"projectId": project_id, "name": b.get("name"),
                                     "isOwn": b.get("isOwn")})
        print(f"{b['id']}  {b.get('name')}" + ("  (own)" if b.get("isOwn") else ""))
    return data


def list_topics(project_id):
    """GET /topics — topics in a project."""
    data = request("GET", "/topics", params={"projectId": project_id})
    items = data if isinstance(data, list) else data.get("topics", [])
    for t in items:
        remember("topics", t["id"], {"projectId": project_id, "name": t.get("name")})
        print(f"{t['id']}  {t.get('name')}")
    return data


def list_prompts(project_id, topic_id=None):
    """GET /prompts — prompts in a project, optionally filtered by topic."""
    data = request("GET", "/prompts", params={"projectId": project_id, "topicId": topic_id})
    items = data if isinstance(data, list) else data.get("prompts", [])
    for p in items:
        remember("prompts", p["id"], {"projectId": project_id, "topicId": p.get("topicId"),
                                      "promptTemplate": p.get("promptTemplate")})
        print(f"{p['id']}  {p.get('promptTemplate')}")
    return data


# --------------------------------------------------------------------------- #
# Updates (PUT) — each asks for the fields interactively, then confirms before sending
# --------------------------------------------------------------------------- #

PLATFORMS = ["chatgpt_app", "claude", "gemini_app", "grok_app", "grok_api",
             "perplexity_app", "google_app", "deepseek", "chatgpt", "gemini", "perplexity"]


def update_project(project_id):
    """PUT /projects/{id} — update a project's name, url, location or languages."""
    current = load_cache()["projects"].get(project_id, {})
    print(f"Updating project {project_id}. Leave blank to keep, '-' to clear.")
    body = {}
    name = ask("Name", current.get("name"))
    if name and name != "-":
        body["name"] = name
    for field in ("url", "location", "languages"):
        value = ask(field.capitalize(), current.get(field))
        if value:
            body[field] = None if value == "-" else value
    if not body:
        sys.exit("Nothing to update.")

    show(body)
    if not confirm("Send this update?"):
        sys.exit("Cancelled.")
    data = request("PUT", f"/projects/{project_id}", body=body)
    remember("projects", project_id, {**current, **{k: data.get(k) for k in
                                                   ("name", "url", "location", "languages",
                                                    "activePlatforms")}})
    show(data)
    return data


def update_platforms(project_id):
    """PUT /projects/{id}/platforms — set which AI platforms the project runs on."""
    current = load_cache()["projects"].get(project_id, {}).get("activePlatforms")
    print(f"Available: {', '.join(PLATFORMS[:8])} (legacy: {', '.join(PLATFORMS[8:])})")
    value = ask("Active platforms, separated by spaces or commas",
                " ".join(current) if current else None)
    if not value:
        sys.exit("Nothing to update.")
    platforms = value.replace(",", " ").split()
    unknown = [p for p in platforms if p not in PLATFORMS]
    if unknown:
        sys.exit(f"Unknown platform(s): {', '.join(unknown)}")

    body = {"activePlatforms": platforms}
    show(body)
    if not confirm("Send this update?"):
        sys.exit("Cancelled.")
    data = request("PUT", f"/projects/{project_id}/platforms", body=body)
    cache = load_cache()
    cache["projects"].setdefault(project_id, {})["activePlatforms"] = data.get("activePlatforms")
    save_cache(cache)
    show(data)
    return data


def update_prompt(project_id, prompt_id=None):
    """PUT /prompts — update a prompt's text, attributes or active flag."""
    cached = load_cache()["prompts"]
    if not prompt_id:
        for pid, p in cached.items():
            if p.get("projectId") == project_id:
                print(f"{pid}  {p.get('promptTemplate')}")
        prompt_id = ask("Prompt ID")
        if not prompt_id:
            sys.exit("A prompt ID is required. Run `prompts` to list them.")
    current = cached.get(prompt_id, {})

    print(f"Updating prompt {prompt_id}. Leave blank to keep.")
    body = {}
    text = ask("Prompt text", current.get("promptTemplate"))
    if text:
        body["promptTemplate"] = text
    attrs = ask("Attributes, comma separated ('-' to clear)",
                ", ".join(current["attributes"]) if current.get("attributes") else None)
    if attrs:
        body["attributes"] = [] if attrs == "-" else [a.strip() for a in attrs.split(",") if a.strip()]
    active = ask("Active? (y/n)")
    if active:
        body["isActive"] = active.lower().startswith("y")
    if not body:
        sys.exit("Nothing to update.")

    show(body)
    if not confirm("Send this update?"):
        sys.exit("Cancelled.")
    data = request("PUT", "/prompts", params={"id": prompt_id}, body=body, allow=(409,))

    # Editing text on a prompt that already has results needs an explicit choice.
    if data.get("requiresConfirmation"):
        show(data)
        print("This prompt already has results.\n"
              "  clone     — create a new prompt and deactivate the old one, keeping its history (recommended)\n"
              "  overwrite — edit in place (not allowed while a run is in progress)")
        choice = (ask("clone / overwrite / cancel") or "cancel").lower()
        if choice not in ("clone", "overwrite"):
            sys.exit("Cancelled.")
        body["confirmClone" if choice == "clone" else "confirmOverwrite"] = True
        data = request("PUT", "/prompts", params={"id": prompt_id}, body=body)

    remember("prompts", data.get("id", prompt_id), {
        "projectId": project_id,
        "topicId": data.get("topicId", current.get("topicId")),
        "promptTemplate": data.get("promptTemplate"),
        "attributes": data.get("attributes"),
    })
    if data.get("cloned"):
        print(f"Cloned: new prompt {data.get('id')} replaces {data.get('originalPromptId')}")
    show(data)
    return data


# --------------------------------------------------------------------------- #
# Account
# --------------------------------------------------------------------------- #

def limits():
    """GET /me/limits — your rate limits and quotas."""
    data = request("GET", "/me/limits")
    show(data)
    return data


def usage(start_date=None, end_date=None, run_id=None):
    """GET /usage — token usage and scraper spend."""
    data = request("GET", "/usage",
                   params={"startDate": start_date, "endDate": end_date, "promptRunId": run_id})
    show(data)
    return data


def allowed_platforms():
    """GET /settings/platforms — platforms your account may use."""
    data = request("GET", "/settings/platforms")
    show(data)
    return data


def show_cache():
    """Print cache.json without calling the API (free)."""
    data = load_cache()
    show(data)
    return None  # nothing new to save


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    parser = argparse.ArgumentParser(description="OpenLens API playground")
    sub = parser.add_subparsers(dest="command", required=True)

    def cmd(name, help_text, project=True, run=False):
        p = sub.add_parser(name, help=help_text)
        if project:
            p.add_argument("--project", help="Project ID (defaults to last used, from cache.json)")
        if run:
            p.add_argument("--run", help="Run ID (defaults to the latest run)")
        return p

    cmd("cache", "Show cached IDs (no API call)", project=False)
    cmd("projects", "List your projects", project=False)
    cmd("limits", "Show your rate limits and quotas", project=False)
    cmd("allowed-platforms", "List the platforms your account may use", project=False)
    p = cmd("usage", "Token usage and scraper spend", project=False)
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--run")

    p = cmd("run-start", "Start (or resume) a prompt run — COSTS MONEY")
    p.add_argument("--platforms", nargs="+", help="e.g. chatgpt_app claude perplexity_app")
    p.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")
    cmd("run-cancel", "Cancel the running run")
    cmd("run-status", "Poll the status of a run", run=True)
    p = cmd("runs", "List run history")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--status")
    p = cmd("results", "Raw platform responses with citations", run=True)
    p.add_argument("--platform")
    p.add_argument("--topic")
    p.add_argument("--limit", type=int)

    p = cmd("visibility", "Visibility scores", run=True)
    p.add_argument("--topic")
    p = cmd("trends", "Visibility over time")
    p.add_argument("--brand")
    p.add_argument("--days", type=int)
    p.add_argument("--compare", help="e.g. 'true' to compare all competitors")
    cmd("engines", "Per-platform source behavior", run=True)
    p = cmd("topic-insight", "AI insight paragraph for a topic", run=True)
    p.add_argument("--topic", required=True)

    p = cmd("mentions", "Top topics where your brand was mentioned", run=True)
    p.add_argument("--limit", type=int)
    p = cmd("sources", "Top cited domains", run=True)
    p.add_argument("--platform")
    p.add_argument("--limit", type=int)

    p = cmd("report", "Download the PDF visibility report")
    p.add_argument("--run", required=True)

    cmd("platforms", "Active platforms for a project")
    cmd("brands", "List brands")
    cmd("topics", "List topics")
    p = cmd("prompts", "List prompts")
    p.add_argument("--topic")

    p = cmd("update", "Interactively update a project, its platforms, or a prompt")
    p.add_argument("target", choices=["project", "platforms", "prompt"],
                   help="What to update")
    p.add_argument("--prompt", help="Prompt ID (for target 'prompt'; asked for if omitted)")
    return parser


def main():
    args = build_parser().parse_args()
    c = args.command
    pid = resolve_project(args.project) if hasattr(args, "project") else None

    if c == "run-start" and not args.yes:
        answer = input(f"Start a run for project {pid}? This uses paid credits. [y/N] ")
        if answer.strip().lower() != "y":
            sys.exit("Cancelled.")

    commands = {
        "cache": show_cache,
        "projects": list_projects,
        "limits": limits,
        "allowed-platforms": allowed_platforms,
        "usage": lambda: usage(args.start_date, args.end_date, args.run),
        "run-start": lambda: start_run(pid, args.platforms),
        "run-cancel": lambda: cancel_run(pid),
        "run-status": lambda: run_status(pid, args.run),
        "runs": lambda: list_runs(pid, args.limit, args.status),
        "results": lambda: run_results(pid, args.run, args.platform, args.topic, args.limit),
        "visibility": lambda: visibility(pid, args.run, args.topic),
        "trends": lambda: visibility_trends(pid, args.brand, args.days, args.compare),
        "engines": lambda: engine_insights(pid, args.run),
        "topic-insight": lambda: topic_insight(pid, args.topic, args.run),
        "mentions": lambda: brand_mentions(pid, args.run, args.limit),
        "sources": lambda: sources(pid, args.run, args.platform, args.limit),
        "report": lambda: download_report(pid, args.run),
        "platforms": lambda: project_platforms(pid),
        "brands": lambda: list_brands(pid),
        "topics": lambda: list_topics(pid),
        "prompts": lambda: list_prompts(pid, args.topic),
        "update": lambda: {
            "project": lambda: update_project(pid),
            "platforms": lambda: update_platforms(pid),
            "prompt": lambda: update_prompt(pid, args.prompt),
        }[args.target](),
    }

    data = commands[c]()
    if data is not None:
        save_output(f"update-{args.target}" if c == "update" else c, data)


if __name__ == "__main__":
    main()
