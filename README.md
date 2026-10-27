# Openlens-Playground
Openlens-Playground is a simple tool written in python to utilize the Openlens API from a command line. Each API call is contained in one function and exists as an argument to the main function call. To reduce token cost simple caching is implemented. Each command produces a json output in the `output/` directory.
## Usage
### Installation
Openlens-playground contains a script at the top of `main.py` allowing compatibility with pipx. 

Clone the repository and make a proper `.env` file with the API key based on `.env.example`
#### Using Pip
Make a virtual environment if you haven't already. 
```
python3 -m venv .venv
source .venv/bin/activate
```
Install requirements
```
pip3 install -r requirements.txt
```
Run command 
```
python3 main.py projects
```
#### Using Pipx
```
pipx run main.py projects
```
### Arguments 
Run any command as `python3 main.py <command> [options]` (or `pipx run main.py <command> [options]`). `python3 main.py <command> --help` lists the options for a single command.

**Common options**

| Option | Applies to | Description |
|---|---|---|
| `--project <id>` | Every command except `cache`, `projects`, `limits`, `allowed-platforms` and `usage` | Project ID to use. If omitted, the last project used (stored as `lastProjectId` in `cache.json`) is used. Run `projects` first to fill the cache. |
| `--run <id>` | Commands that read run data (see below) | Run ID to read from. If omitted, the API uses the latest usable run. |

**Commands**

| Command | Options | Calls the API | Description |
|---|---|---|---|
| `cache` | — | No | Prints `cache.json`: cached project, run, topic, brand and prompt IDs. |
| `projects` | — | Yes | Lists your projects and caches their IDs. Sets the default project if you have only one. |
| `limits` | — | Yes | Shows your account's rate limits and quotas. |
| `allowed-platforms` | — | Yes | Lists the AI platforms your account is allowed to use. |
| `usage` | `--start-date <date>` start of the range<br>`--end-date <date>` end of the range<br>`--run <id>` only usage from this run | Yes | Shows token usage and scraper spend, grouped by model and call type. |
| `run-start` | `--project <id>`<br>`--platforms <p1> <p2> ...` platforms to query, e.g. `chatgpt_app claude perplexity_app` (defaults to the project's saved platforms)<br>`-y`, `--yes` skip the confirmation prompt | Yes | Starts a new paid prompt run (the most expensive call), or resumes an interrupted one. Asks for confirmation first. Caches the new run ID. |
| `run-cancel` | `--project <id>` | Yes | Cancels the run currently in progress for the project. |
| `run-status` | `--project <id>`<br>`--run <id>` | Yes | Shows a run's status and how many tasks are complete or failed. |
| `runs` | `--project <id>`<br>`--limit <n>` number of runs to list (default 20)<br>`--status <status>` only runs with this status, e.g. `completed` | Yes | Lists the project's run history and caches the run IDs. |
| `results` | `--project <id>`<br>`--run <id>`<br>`--platform <name>` only this platform<br>`--topic <id>` only this topic<br>`--limit <n>` maximum number of responses | Yes | Prints each AI platform's raw answer with the prompt used. The saved JSON includes the mentions and citations for each answer. |
| `visibility` | `--project <id>`<br>`--run <id>`<br>`--topic <id>` only this topic | Yes | Shows visibility scores for your brand and competitors. |
| `trends` | `--project <id>`<br>`--brand <id>` only this brand<br>`--days <n>` how many days back<br>`--compare <value>` e.g. `true` to include all competitors | Yes | Shows visibility over time. |
| `engines` | `--project <id>`<br>`--run <id>` | Yes | Shows how each AI platform chooses and cites sources. |
| `topic-insight` | `--project <id>`<br>`--run <id>`<br>`--topic <id>` **required** | Yes | Returns an AI-written insight paragraph for one topic. |
| `mentions` | `--project <id>`<br>`--run <id>`<br>`--limit <n>` maximum number of topics | Yes | Lists the topics where your own brand was mentioned, with the URLs cited. |
| `sources` | `--project <id>`<br>`--run <id>`<br>`--platform <name>` only this platform<br>`--limit <n>` maximum number of domains | Yes | Lists the most-cited domains and their URLs. |
| `report` | `--project <id>`<br>`--run <id>` **required** | Yes | Downloads a client-ready PDF visibility report to `output/report_<runId>.pdf`. |
| `platforms` | `--project <id>` | Yes | Shows the project's active platforms and what your account is entitled to. |
| `brands` | `--project <id>` | Yes | Lists your own brand and competitors, and caches their IDs. |
| `topics` | `--project <id>` | Yes | Lists the project's topics and caches their IDs. |
| `prompts` | `--project <id>`<br>`--topic <id>` only prompts in this topic | Yes | Lists the project's prompts and caches their IDs and text. |
| `update project` | `--project <id>` | Yes | Asks for a new name, URL, location and languages, then updates the project. |
| `update platforms` | `--project <id>` | Yes | Asks which AI platforms the project should run on, then sets them. Future runs use these platforms. |
| `update prompt` | `--project <id>`<br>`--prompt <id>` the prompt to edit (asked for if omitted) | Yes | Asks for new prompt text, attributes and whether it's active, then updates the prompt. |

Platform names: `chatgpt_app`, `claude`, `gemini_app`, `grok_app`, `grok_api`, `perplexity_app`, `google_app`, `deepseek` (`chatgpt`, `gemini` and `perplexity` are legacy).

Every command except `cache` saves its full response to `output/<command>_<timestamp>.json`.

#### Updating with `update`

`update` asks for each field one at a time and shows the current value in brackets when it's in `cache.json`. Press Enter to keep a value, or type `-` to clear an optional field (URL, location, languages, attributes). Before anything is sent, it prints the request body and asks for confirmation.

```
python3 main.py update project
python3 main.py update platforms
python3 main.py update prompt --prompt <id>
```

When you change the text of a prompt that already has results, OpenLens asks how to handle the old results. The command then asks you to choose:

- `clone`: creates a new prompt and deactivates the old one, keeping its history. This is recommended for prompts you track over time.
- `overwrite`: edits the prompt in place. This isn't allowed while a run is in progress.

For prompt attributes, the allowed values are set per project in OpenLens.
