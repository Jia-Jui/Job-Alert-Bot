# Job Alert Bot

Job Alert Bot checks public job sources on a schedule, filters for entry-level software roles, stores seen jobs in either a local SQLite file or Firebase Realtime Database, and sends alerts through exactly one user-selected channel: Telegram or email.

## Budget rule

This project is designed to stay at a hard budget of `$0`.

- Prefer running locally on your PC
- GitHub Actions is optional
- Local SQLite for local runs
- Firebase Realtime Database for cloud runs
- No Firebase Storage
- No paid email provider
- No paid server or VPS

## V1 scope

- Lever company boards via public JSON
- Greenhouse boards via public API
- GitHub job-list repositories via raw README parsing
- Keyword include/exclude filtering
- SQLite or Firebase de-duplication
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
```

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
Apply: https://example.com/apply
```

## Source ideas

Included in V1 configuration examples:

- SimplifyJobs New-Grad Positions
- ambicuity New-Grad Jobs
- zapplyjobs New-Grad Software Engineering Jobs
- jobright-ai 2026 Software Engineer New Grad
- speedyapply 2026 SWE College Jobs

These community-maintained repos can be noisy, so they are treated as optional supplemental sources.

