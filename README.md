# RiskRadarPlatform (RRP)

RiskRadarPlatform is a local Flask dashboard that pulls Jira board data from Atlassian Jira Cloud and presents a single-pane view of sprint health, resource capacity, risks, and backlog prioritization.

## Features

- Jira board data import from Atlassian Jira Cloud
- Sprint Health dashboard with velocity and story-point visibility
- Resource Capacity dashboard based on assigned story points
- Risk Identification engine for overloaded users, unassigned critical stories, blocked work, and sprint capacity risk
- Backlog prioritization with priority-based sorting
- CSV export of current Jira issues
- Local web UI running on localhost

## Project goals

This application was designed to support the business requirements described in the project brief:

- Consolidated view across Jira board work items
- Epic, Story, Task, and Bug monitoring
- Sprint health and burn-down tracking
- Capacity planning by team member and role
- Risk highlighting and prioritization
- Alternate resource suggestions based on capacity rules

## Tech stack

- Python 3
- Flask
- Requests
- python-dotenv
- Jira Cloud REST API

## Repository structure

- app.py — Flask application and Jira dashboard logic
- templates/ — HTML dashboard templates
- .env.example — sample Jira configuration template
- README.md — project overview and setup guide
- requirements.txt — app dependencies

## Local setup

1. Create and activate a virtual environment

   Windows PowerShell:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies

   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables

   Copy the sample file and update values:

   ```bash
   copy .env.example .env
   ```

   Then update the values in .env with your Jira credentials:

   ```env
   JIRA_BASE_URL=https://your-company.atlassian.net
   JIRA_EMAIL=your-email@example.com
   JIRA_API_TOKEN=your-api-token
   JIRA_BOARD_ID=67
   ```

4. Run the app locally

   ```bash
   python app.py
   ```

5. Open the dashboard in a browser

   ```text
   http://127.0.0.1:5000
   ```

## Download CSV

The dashboard includes a CSV export button that downloads the current Jira board issues into a CSV file directly from the app.

## Risk logic included

The app includes default rules aligned to the project brief:

- Overloaded user: assigned story points greater than capacity threshold
- Unassigned critical story: high priority and no assignee
- Blocked stories: status equals Blocked
- Excessive bugs: bug count beyond threshold
- Sprint capacity breach: committed story points exceed team capacity

## Important notes

- The .env file is excluded from Git and should never be committed.
- Keep Jira API tokens secure.
- The application is intended for local development and demo use.

## License

This project is for internal evaluation and demonstration purposes.
