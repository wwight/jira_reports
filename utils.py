from collections import defaultdict
from datetime import datetime, timedelta

import yaml


DATE_FORMAT = '%Y-%m-%d'
DONE_STATUSES = set(('done',))
HIGH_P = set(('P0', 'P1', 'P2'))
PROJECTS_FILE = 'projects.yml'
STORY_POINTS_FIELD = 'customfield_10005'


def load_projects(projects_file):
    with open(projects_file) as f:
        return [project for project in yaml.load(f.read())
                if not project.get('disabled')]


def story_points(issue):
    return int(issue['fields'].get(STORY_POINTS_FIELD) or 0)

# ({date1: num_created, date2: num_created, ...},
#  {date1: num_closed, date2: num_closed, ...})
def created_and_closed_by_date(issues, priority_filter, use_story_points=False):
    created_by_date = defaultdict(int)
    closed_by_date = defaultdict(int)

    for issue in issues:
        status = issue['fields']['status']['name'].lower()
        is_done = status in DONE_STATUSES
        priority = issue['fields']['priority']['name']
        if priority in priority_filter:
            value = story_points(issue) if use_story_points else 1
            if not value:
                continue

            created_string = issue['fields']['created'][:10]
            created = datetime.strptime(created_string, DATE_FORMAT).date()
            created_by_date[created] += value
            if is_done:
                closed_string = issue['fields']['resolutiondate'][:10]
                closed = datetime.strptime(closed_string, DATE_FORMAT).date()
                closed_by_date[closed] += value
    return created_by_date, closed_by_date

def devs_per_day(raw_dev_days):
    dev_days = {}
    has_begun = False
    for monday in sorted(raw_dev_days.iterkeys()):
        week_allocation = raw_dev_days[monday]
        weekday = monday
        for daily_devs in week_allocation.split(','):
            devs = int(daily_devs)
            # The first working day might not be on a Monday.
            # Don't start recording dev_days until the first working day.
            has_begun = has_begun or devs
            if has_begun:
                dev_days[weekday] = devs
            weekday += timedelta(days=1)
    return dev_days
