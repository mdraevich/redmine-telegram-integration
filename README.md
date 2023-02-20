# Telegram-Redmine automation for time tracking activity

## Motivation
Time tracking via default Redmine web interface is quite time-consuming and leads to lots of mistakes due to inavailability to edit and delete your issues or log time.

That's a reason why I decided to manage my time tracking activity in smart way via Telegram Channel.
This project is aimed to sync any data between Telegram Channel and Redmine, so you're free of routine to move data manually.

## Architecture
Project consists of two Docker images:
1. **poll_channels** is responsible for interaction with Telegram API in order to export, parse and publish channel posts.
2. **redmine_pusher** is responsible for interaction with Redmine API in order to import data gathered from **poll_channels** HTTP endpoint.

## Usage

Follow these steps to deploy this solution:
1. Create Telegram Channel (either private or public one). 
2. Pull the repository, create environment file and configuration file.
3. Create authentication file for interacting with Telegram API.
4. Run `docker compose up -d --build` to get this stuff up & working.

#### Step #1: Telegram Channel message format

Format depends on **poll_channels** configuration, but here's default one:
```shell
1) 1st line has to have two entries as \d\d:\d\d (regex), other characters are ignored
2) 2-6 lines are parsed as description and parsed as .* (regex)
3) any other next line is ignored
```

#### Step #2: environment and configuration files
Generate an environment file that's required by Docker Compose:
```
# in the root of project

echo "
COMPOSE_PROJECT_NAME=redmine-integration
PYTHONPATH=.
TZ=Europe/Minsk

# poll channels
SESSION_NAME=redmine-integration
LISTEN_ADDRESS=0.0.0.0:8080
PHONE=<YOUR-TELEGRAM-PHONE-NUMBER>
API_ID=<API-ID-FOR-TELEGRAM>
API_HASH=<API-HASH-FOR-TELEGRAM>


# redmine pusher
POLL_CHANNELS_URL=http://telegram-poll-channels:8080/data
REDMINE_ADDR=<REDMINE-ADDRESS in format http://domain-name.com>
REDMINE_API_KEY=<REDMINE-ACCESS-API-KEY>
MAX_DAYS=7
" > .env
```

Generate configuration file that's required by **poll_channels** module based on (example.yml)[./example.yml] file and placed it in `./secrets` directory:
```shell
# in the root of project

mkdir -p ./secrets
cp example.yml ./secrets/config.yml
nano ./secrets/config.yml
```


#### Step #3: create authentication file
In order to be working **poll_channels** modules needs Telegram account to access Telegram API. Follow the authentication process to create a session file: 

```shell
# in the project root directory

mkdir -p ./secrets
pipenv install
pipenv run python3 session_handler/main.py
```


## Q&A

**Q:** What data is **NOT** pushed to Redmine?
**A:** Data is **NOT** pushed for today; data is **NOT** pushed for the days after **MAX_DAYS** env variable; data is **NOT** pushed for the days which equal to `start_date` value for any of the last 15 issues. Other data is pushed to a newly created issue with `start_date` set to the published day of data in your Telegram Channel.
