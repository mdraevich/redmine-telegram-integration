import os
import time
import json
import datetime
import logging
from urllib import request, error
from redminelib import Redmine


LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=LOGLEVEL
)
logger = logging.getLogger(__name__)


def get_channel_data():
    """
    gathers JSON file from HTTP endpoint containing 
    posts for all configured channels
    """
    try:
        contents = request.urlopen(poll_channel_url).read()
        data = json.loads(contents)
    except (ConnectionError, error.URLError) as exc:
        return (False, None)
    return (True, data)


def process_channel_data_element(element):
    """
    takes a single element of channel data object and transforms it 
    """

    if "timestamp" not in element or "matches" not in element:
        return None
    if len(element["matches"][0]) < 2:
        return None

    # TODO, needs to be handled by try-except block
    from_timestamp = datetime.datetime(2023,1,1,
                        hour=int(element["matches"][0][0].split(":")[0]),
                        minute=int(element["matches"][0][0].split(":")[1]))
    to_timestamp = datetime.datetime(2023,1,1,
                        hour=int(element["matches"][0][1].split(":")[0]),
                        minute=int(element["matches"][0][1].split(":")[1]))

    if from_timestamp > to_timestamp:
        # to_timestamp should be within the same day,
        # but it's related to the next day, so change day number
        to_timestamp = datetime.datetime(2023,1,2,
                        hour=int(element["matches"][0][1].split(":")[0]),
                        minute=int(element["matches"][0][1].split(":")[1]))

    formatted_element = {
        "message_timestamp": datetime.datetime.fromtimestamp(element["timestamp"]),
        "job_start": element["matches"][0][0],
        "job_stop": element["matches"][0][1],
        "job_amount": (to_timestamp - from_timestamp).total_seconds() / 60 / 60,
        "job_description": " ".join(
                        list(map(" ".join, element["matches"][1:]))).strip()
    } 
    return formatted_element

def process_channel_data(data):
    """
    takes channel data object and transforms it 
    """

    formatted_data = list(map(process_channel_data_element, data))
    return formatted_data


def get_issues(redmine_address, project_id, limit, **kwargs):
    """
    returns issues
    """ 
    redmine = Redmine(redmine_address,
                      key=kwargs["redmine_api_key"])

    return redmine.issue.filter(project_id=project_id,
                                status_id="*",
                                limit=limit)


def create_issue(redmine_address, project_id, subject, **kwargs):
    """
    creates issue in redmine via REST API
    """
    redmine = Redmine(redmine_address,
                      key=kwargs["redmine_api_key"])
    return redmine.issue.create(
        project_id=project_id,
        subject=subject,
        tracker_id=kwargs["tracker_id"],
        status_id=kwargs["status_id"],
        priority_id=kwargs["priority_id"],
        start_date=kwargs["start_date"],
        assigned_to_id=kwargs["assigned_to_id"],
        estimated_hours=kwargs["estimated_hours"]
    )


def log_time_in_issue(redmine_address, issue_id, hours, **kwargs):
    """
    log time within the specified issue id
    """
    redmine = Redmine(redmine_address,
                      key=kwargs["redmine_api_key"])
    return redmine.time_entry.create(
        issue_id=issue_id,
        spent_on=kwargs["start_date"],
        hours=hours,
        activity_id=kwargs["activity_id"],
        user_id=kwargs["user_id"],
        comments=kwargs["description"]
    )


if __name__ == '__main__':
    poll_channel_url = os.environ.get("POLL_CHANNELS_URL", None)
    redmine_address = os.environ.get("REDMINE_ADDR", "")
    redmine_username = os.environ.get("REDMINE_USERNAME", "")
    redmine_password = os.environ.get("REDMINE_PASSWORD", "")
    redmine_api_key = os.environ.get("REDMINE_API_KEY", "")
    max_days = int(os.environ.get("MAX_DAYS", "7"))
    poll_interval = int(os.environ.get("POLL_INTERVAL", "1800"))

    while True:
        success, data_obj = get_channel_data()
        if success:
            logger.info("Success to retrieve data, try to format it")

            for channel in data_obj["channels"]:
                logger.debug(process_channel_data(channel["data"]))
                
                created_issues = get_issues(redmine_address,
                                    channel["tags"]["project_id"],
                                    limit=15,
                                    redmine_api_key=redmine_api_key)
                logger.debug([ i.subject for i in created_issues ])

                # dict of lists,
                # key = issue.start_day
                # value = list() of time events
                events_to_push = {}
                today = datetime.datetime.today()
                for element in process_channel_data(channel["data"]):
                    if element is None:
                        # element was parsed incorrectly
                        logger.warning("Channel data element was parsed "
                                       "incorrectly, skip it") 
                        continue

                    el_datetime = element["message_timestamp"]
                    el_date = el_datetime.date()
                    if el_datetime.day == today.day:
                        # skip pushing time events for today
                        logger.info("%s: skip pushing events for today",
                                    el_date.strftime("%d.%m.%Y"))
                        continue
                    if (today.date() - el_date).days > max_days:
                        logger.info("%s: skip outdated events (MAX_DAYS=%s)",
                                    el_date.strftime("%d.%m.%Y"),
                                    max_days)
                        # skip pushing outdated time events
                        continue

                    is_issue_created = any(
                        [i.start_date == el_date for i in created_issues])
                    logger.info("%s: is_issue_created=%s",
                                   el_date.strftime("%d.%m.%Y"),
                                   is_issue_created)

                    if is_issue_created: 
                        # we're not going to recreate issue
                        # neither pushing time events to it
                        continue

                    # if issue is not already created 
                    # and it's not today and it's not outdated event,
                    # then add event to push later outside of for-cycle
                    key = el_date.strftime("%d.%m.%Y")
                    if key not in events_to_push:
                        events_to_push[key] = []
                    events_to_push[key].append(element)

                logger.debug(events_to_push)
                for key, value in events_to_push.items():
                    key_date = datetime.datetime.strptime(key, "%d.%m.%Y").date()
                    issue = create_issue(
                                redmine_address,
                                channel["tags"]["project_id"],
                                "{}: automated by redmine-pusher".format(key),
                                redmine_api_key=redmine_api_key,
                                tracker_id=channel["tags"]["tracker_id"],
                                status_id=channel["tags"]["status_id"],
                                priority_id=channel["tags"]["priority_id"],
                                start_date=key_date,
                                assigned_to_id=channel["tags"]["user_id"],
                                estimated_hours=8)

                    for event in value:
                        log_time_in_issue(
                                redmine_address,
                                issue_id=issue.id,
                                hours=event["job_amount"],
                                redmine_api_key=redmine_api_key,
                                start_date=key_date,
                                activity_id=channel["tags"]["activity_id"],
                                user_id=channel["tags"]["user_id"],
                                description=event["job_description"])
        else:
            logger.error("Failed to retrieve data")
        time.sleep(poll_interval)