# Job Alert Bot

Job Alert Bot checks public job sources on a schedule, resolves the safest public apply link it can find, ranks jobs for early-career software roles, stores seen jobs in either a local SQLite file or Firebase Realtime Database, and sends alerts through exactly one user-selected channel: Telegram or email.

## Budget rule

This project is designed to stay at a hard budget of `$0`.

- Prefer running locally on your PC
- GitHub Actions is optional
- Local SQLite for local runs
- Firebase Realtime Database for cloud runs
- No Firebase Storage
- No paid email provider
- No paid server or VPS

## Closed-loop workflow

The project is now designed around a closed review loop:

1. Discover jobs from public sources
2. Resolve the best public apply link without bypassing anti-bot protections
3. Rank jobs with explainable scoring
4. Notify you about stronger matches
5. Store job metadata and application status
6. Let you review, save, apply, reject, or close jobs from CLI or local UI
7. Reuse those outcomes in future review sessions

## Scope

- Lever company boards via public JSON
- Greenhouse boards via public API
- GitHub job-list repositories via raw README parsing
- Safe public link resolution with redirect and HTML fallback
- Explainable ranking and score reasons
- Keyword include/exclude filtering
- SQLite or Firebase de-duplication
- Optional application status tracking by job dedupe key
- Telegram or email alerts
- Local PC scheduled runs
- GitHub Actions scheduled runs

## Anti-bot approach

This project is designed to reduce bot-trigger risk instead of trying to bypass anti-bot systems.

- Prefer official or public machine-readable endpoints:
  - Lever: `https://jobs.lever.co/<company>?mode=json`
  - Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<board>/jobs`
  - GitHub repos: raw README content
- Keep traffic low:
  - Run every 30 to 60 minutes
  - Add small per-request delays
  - Use request timeouts
- Be transparent:
  - Use a normal descriptive user agent
  - Do not rotate proxies
  - Do not attempt CAPTCHA evasion
- Only inspect public pages and URLs:
  - Prefer API-provided links
  - Follow normal redirects
  - Parse public HTML for likely apply links
  - Keep advanced multi-page discovery opt-in only
- Cache and de-duplicate:
  - Only alert on unseen jobs
  - Prefer stable source IDs where available

If a company page blocks even low-rate requests, the safest next step is to remove that source or switch to an official feed/API.

## Project layout

```text
.github/workflows/check-jobs.yml
companies.example.json
requirements.txt
src/job_alert_bot/
```

## Configuration

Copy the example config and adjust targets:

```powershell
Copy-Item companies.example.json companies.json
```

For local runs, copy the PowerShell settings template:

```powershell
Copy-Item local.settings.example.ps1 local.settings.ps1
```

Then edit `local.settings.ps1`.

If you prefer setting environment variables manually, use:

```powershell
$env:JOB_ALERT_COMPANIES_FILE="companies.json"
$env:JOB_ALERT_ENABLED="true"
$env:JOB_ALERT_STORAGE_MODE="sqlite"
$env:JOB_ALERT_SQLITE_DB_PATH="jobs.db"
$env:JOB_ALERT_NOTIFICATION_CHANNEL="email"
$env:EMAIL_SMTP_HOST="smtp.gmail.com"
$env:EMAIL_SMTP_PORT="587"
$env:EMAIL_SMTP_USERNAME="your-email@example.com"
$env:EMAIL_SMTP_PASSWORD="your-app-password"
$env:EMAIL_FROM_ADDRESS="your-email@example.com"
$env:EMAIL_TO_ADDRESS="your-destination@example.com"
$env:EMAIL_USE_TLS="true"
```

If you want Telegram instead of email:

```powershell
$env:JOB_ALERT_NOTIFICATION_CHANNEL="telegram"
$env:TELEGRAM_BOT_TOKEN="your-bot-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
```

If you want Firebase instead of local SQLite:

```powershell
$env:JOB_ALERT_STORAGE_MODE="firebase"
$env:FIREBASE_DATABASE_URL="https://your-project-default-rtdb.firebaseio.com"
$env:FIREBASE_SERVICE_ACCOUNT_JSON="your-service-account-json"
```

Optional environment variables:

```text
JOB_ALERT_STORAGE_MODE
JOB_ALERT_SQLITE_DB_PATH
JOB_ALERT_FRESH_WINDOW_MINUTES
JOB_ALERT_MIN_MATCH_SCORE
JOB_ALERT_PREFERRED_LOCATIONS
JOB_ALERT_INCLUDE_KEYWORDS
JOB_ALERT_EXCLUDE_KEYWORDS
JOB_ALERT_REQUEST_DELAY_SECONDS
JOB_ALERT_TIMEOUT_SECONDS
JOB_ALERT_GITHUB_RAW_URLS
JOB_ALERT_ENABLE_ADVANCED_LINK_DISCOVERY
JOB_ALERT_LINK_DISCOVERY_TIMEOUT_SECONDS
JOB_ALERT_LINK_DISCOVERY_MAX_PAGES
JOB_ALERT_COMPANY_PRIORITIES
JOB_ALERT_PREFERRED_COMPANIES
```

Optional ranking and link-resolution tuning:

- `JOB_ALERT_COMPANY_PRIORITIES`
  A JSON object mapping company names to integer priority bonuses, for example `{"stripe": 2, "cloudflare": 2}`.
- `JOB_ALERT_PREFERRED_COMPANIES`
  A comma-separated list reserved for future workflow tuning.
- `JOB_ALERT_ENABLE_ADVANCED_LINK_DISCOVERY`
  Defaults to `false`. When `true`, the resolver may inspect additional public pages linked from the original public posting, up to the configured page limit.
- `JOB_ALERT_LINK_DISCOVERY_TIMEOUT_SECONDS`
  Timeout for redirect and public HTML resolution work.
- `JOB_ALERT_LINK_DISCOVERY_MAX_PAGES`
  Maximum number of extra public pages to inspect when advanced discovery is enabled.

## Run mode options

You can choose either mode:

1. Local on your PC
2. GitHub Actions

### Local on your PC

Best choice if you want the clearest `$0` setup.

- No GitHub Actions dependency
- No cloud scheduler dependency
- Uses a local SQLite file by default
- Firebase is optional, not required
- Your computer must be on when the scheduled check runs
- Your email credentials stay on your PC if you keep using `local.settings.ps1`

Install dependencies and run once:

```powershell
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

If `python` is not on your PATH, pass your interpreter explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1 -PythonCommand "C:\Path\To\python.exe"
```

To verify email without waiting for a new job match:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\send-test-email.ps1
```

### Schedule local runs on Windows

Use Windows Task Scheduler:

1. Open Task Scheduler
2. Create Task
3. Name it `Job Alert Bot`
4. Add a trigger:
   - Daily
   - Repeat task every `30 minutes`
   - For a duration of `1 day`
5. Add an action:
   - Program/script: `powershell.exe`
   - Add arguments:

```text
-ExecutionPolicy Bypass -File "<your-repo-path>\scripts\run-local.ps1"
```

6. Save the task

To stop local runs later:

- Disable the scheduled task in Task Scheduler
- Or set `$env:JOB_ALERT_ENABLED = "false"` inside `local.settings.ps1`

Local data safety:

- `local.settings.ps1` is ignored by git and stays on your PC
- `jobs.db` stays on your PC when using `sqlite` mode
- Do not upload `local.settings.ps1` to GitHub
- If you use email, prefer an app password instead of your main mailbox password

### GitHub Actions

Best choice if you want it running without your PC being on.

- Works on GitHub's servers
- Repo should stay public to remain free on standard runners
- Uses Firebase Realtime Database for seen-job tracking
- Email or Telegram credentials live in GitHub Actions secrets, not in the repo

The current workflow runs at about every 30 minutes:

- `17` minutes past each hour
- `47` minutes past each hour

To stop GitHub Actions later:

- Set the `JOB_ALERT_ENABLED` secret to `false`
- Or disable the workflow in the GitHub Actions UI

Notification behavior:

- Set `JOB_ALERT_ENABLED=false` to pause the bot without removing the workflow
- Set `JOB_ALERT_STORAGE_MODE=sqlite` for local-only storage
- Set `JOB_ALERT_STORAGE_MODE=firebase` for Firebase storage
- Set `JOB_ALERT_FRESH_WINDOW_MINUTES=60` to treat jobs newer than 60 minutes as immediate alerts
- Set `JOB_ALERT_MIN_MATCH_SCORE=4` to require a stronger title/location fit before sending
- Set `JOB_ALERT_PREFERRED_LOCATIONS` to order where you want alerts prioritized
- Set `JOB_ALERT_NOTIFICATION_CHANNEL=telegram` to send Telegram only
- Set `JOB_ALERT_NOTIFICATION_CHANNEL=email` to send email only
- The app does not send both
- Firebase is only required when storage mode is `firebase`
- The app fails fast if the selected channel is missing required settings
- Older or unknown-age unseen jobs are bundled into one digest email instead of many individual emails
- Duplicate links within the same run are skipped before sending
- Jobs are sorted by your preferred locations before alerts are sent
- Alerts include score, ranking reason, best available apply link, original job link when different, and link confidence when available

## Link resolution

Each job can now carry:

- `public_job_url`
- `resolved_apply_url`
- `referral_or_tracking_url`
- `link_source`
- `link_confidence`
- `link_resolution_notes`

Resolution order:

1. Official API-provided public/apply URL
2. Normal HTTP redirect target
3. Public job detail page HTML parsing
4. Optional advanced public multi-page discovery when explicitly enabled

If nothing better is found, the bot falls back to the original job URL.

Confidence levels:

- `high`
- `medium`
- `low`

The project does not use CAPTCHA evasion, login-only scraping, rotating proxies, or anti-bot bypass behavior.

## Ranking

Ranking is explainable and now considers:

- title match
- early-career vs. seniority hints
- preferred locations
- remote/hybrid signal
- posting freshness
- company priority bonuses
- apply-link confidence
- exclusion flags

A stored reason string looks like:

```text
Strong title match, preferred location, fresh posting, direct apply link found.
```

## Application status tracking

Application tracking is stored separately from seen-job de-duplication so it does not interfere with alerts or existing dedupe behavior.

- Status is keyed by the job `dedupe_key`, which is `source:external_id`
- Local mode stores statuses in the same SQLite database file
- Firebase mode stores statuses in a separate `/job_statuses` path
- Supported statuses:
  - `saved`
  - `applied`
  - `interview`
  - `in progress`
  - `rejected`
  - `offer`
  - `closed`

Examples:

```powershell
python -m job_alert_bot ui serve
python -m job_alert_bot seen list
python -m job_alert_bot queue review
python -m job_alert_bot status set "lever:abc123" applied
python -m job_alert_bot status applied "lever:abc123"
python -m job_alert_bot status get "lever:abc123"
python -m job_alert_bot status list
python -m job_alert_bot status list --status applied
python -m job_alert_bot status board
python -m job_alert_bot status active
```

`ui serve` starts a local click-based dashboard at `http://127.0.0.1:8765`. It uses the same SQLite or Firebase storage as the CLI commands, and it is intended for manual local use only.

`seen list` is the easiest local lookup flow. It shows tracked jobs with their `dedupe_key` and current saved status, so you can copy the key into `status set`.

`queue review` is the manual apply queue. It shows jobs whose `posted_at` or `first_seen_at` is at least 60 minutes old and that are still un-applied, so you can run it only when you are ready to review older openings.

`queue review` now also shows the ranking reason, score, confidence, and best available apply link.

Status shortcuts are available for faster updates:

```powershell
python -m job_alert_bot status saved "lever:abc123"
python -m job_alert_bot status applied "lever:abc123"
python -m job_alert_bot status interview "lever:abc123"
python -m job_alert_bot status in-progress "lever:abc123"
python -m job_alert_bot status rejected "lever:abc123"
python -m job_alert_bot status offer "lever:abc123"
python -m job_alert_bot status closed "lever:abc123"
```

Default bot runs are unchanged:

```powershell
python -m job_alert_bot
python -m job_alert_bot run
```

## Review and apply workflow

Recommended manual loop:

1. Let the scheduled bot collect and notify
2. Open the local dashboard:

```powershell
python -m job_alert_bot ui serve
```

3. Review the queue of older un-applied jobs
4. Open the best available apply link
5. Mark the result:
   - `saved`
   - `applied`
   - `interview`
   - `rejected`
   - `offer`
   - `closed`

The local UI and CLI both use the same stored job metadata and status records.

Default include keywords:

- Software Engineer
- Backend
- Python
- AWS
- API
- Serverless
- Full Stack
- Entry Level
- Junior
- New Grad

Default exclude keywords:

- Senior
- Staff
- Principal
- Lead
- Manager
- Director
- Architect
- 5+ years
- 6+ years
- 7+ years
- Frontend
- iOS
- Android
- Mobile
- React Native
- Security
- Cyber
- QA
- SDET
- Test Engineer
- Data Scientist
- Machine Learning
- ML Engineer
- DevOps
- Site Reliability
- SRE
- clearance
- citizenship required

## GitHub Actions setup

Add these repository secrets:

- `JOB_ALERT_COMPANIES_JSON`
- `JOB_ALERT_ENABLED`
- `JOB_ALERT_STORAGE_MODE`
- `JOB_ALERT_NOTIFICATION_CHANNEL`
- `FIREBASE_DATABASE_URL`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`
- `EMAIL_SMTP_USERNAME`
- `EMAIL_SMTP_PASSWORD`
- `EMAIL_FROM_ADDRESS`
- `EMAIL_TO_ADDRESS`
- `EMAIL_USE_TLS`

`JOB_ALERT_COMPANIES_JSON` should contain the full JSON from `companies.json`.

`FIREBASE_SERVICE_ACCOUNT_JSON` should contain the full service account JSON as a single secret value.

Recommended mode split:

- Local PC: `JOB_ALERT_STORAGE_MODE=sqlite`
- GitHub Actions: `JOB_ALERT_STORAGE_MODE=firebase`

For a strict `$0` setup:

- Keep the repository public
- Keep the job check interval at 30 to 60 minutes
- Keep the number of target companies modest for V1

## Example alert

```text
New Job Match
Company: GitKraken
Role: Software Engineer
Location: Remote
Score: 10
Why: Strong title match, preferred location, fresh posting, direct apply link found.
Best apply link: https://example.com/apply
Original job link: https://example.com/jobs/123
Link confidence: high
```

## Source ideas

Included in V1 configuration examples:

- SimplifyJobs New-Grad Positions
- ambicuity New-Grad Jobs
- zapplyjobs New-Grad Software Engineering Jobs
- jobright-ai 2026 Software Engineer New Grad
- speedyapply 2026 SWE College Jobs

These community-maintained repos can be noisy, so they are treated as optional supplemental sources.

