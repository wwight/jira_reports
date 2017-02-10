#!/usr/bin/python

# The following Python libraries are required to run this script.
# http://docs.python-requests.org/en/master/
# http://matplotlib.org/
# http://pyyaml.org/
#
# To install:
#     `sudo pip install requests`
#     `sudo pip install matplotlib`
#     `sudo pip install pyyaml`


from argparse import ArgumentParser
from collections import defaultdict, deque
from datetime import date, timedelta
from itertools import chain
import math
import os

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as plticker

from utils import created_and_closed_by_date, devs_per_day, load_projects, DATE_FORMAT, PROJECTS_FILE, HIGH_P
from jira_connect import JIRA


BAR_WIDTH = 0.7  # for bar charts
GRAPH_COLORS = {-2: '#ff7043', -1: '#dddddd', 0: '#99bad7', 1: '#6a93b9', 2: '#2a5e8d', 3: '#073763', 4: '#011a30', 5: '#33cc33'}
GRAPH_LABELS = {-2: 'New This Week', -1: 'Remain Last Week', 0: 'Done This Week', 1: '1 Week Ago', 2: '2 Weeks Ago', 3: '3 Weeks Ago', 4: '4 Weeks Ago'}
GRAPH_DIR = 'graphs'
GRID_WIDTH = 20

MONTHS = mdates.MonthLocator()
MONTHS_FORMAT = mdates.DateFormatter('')
ONE_WEEK = 7
WEEKS = mdates.DayLocator(interval=7)
WEEKS_FORMAT = mdates.DateFormatter('%b\n%-d')


def collect_options():
    parser = ArgumentParser()
    parser.add_argument(
        'config_file', help='The config file to parse.')
    parser.add_argument(
        'projects_file', help='The project file to parse.')
    parser.add_argument(
        '-a', '--all_reports', action='store_true',
        help='Skip interactive mode and run all reports.')
    parser.add_argument(
        '-c', '--use-cache', action='store_true',
        help='Used cached JIRA data to avoid making live queries. Useful for testing')

    return parser.parse_args()

def prompt_for_choices(choices, choice_names, prompt):
    numbers_to_choices = {str(n): choice for n, choice in enumerate(choices, 1)}
    for number, choice in enumerate(choice_names, 1):
        print '%i) %s' % (number, choice)
    chosen_number = -1
    while chosen_number and chosen_number not in numbers_to_choices:
        chosen_number = raw_input('%s\n? ' % prompt)
    print ''
    return numbers_to_choices.get(chosen_number)

def prompt_for_projects(projects):
    prompt = 'Enter the number of the project you want to report on, or press return to report on all projects.'
    project = prompt_for_choices(projects, (p['name'] for p in projects), prompt)
    return [project] if project else projects

def prompt_for_graph_type():
    choices = ('projects', 'issues', 'points', 'completion')
    choice_names = ('Projects', 'Issue Burnup', 'Points Completed', 'Completion Prediction')
    prompt = 'Enter the number of the graph type you want to report on, or press return to render all graphs.'
    return prompt_for_choices(choices, choice_names, prompt)

def graph_file(graph_type):
    def name2file(string):
        return string.replace(' ', '-').lower()
    date_string = date.today().strftime(DATE_FORMAT)
    file_name = name2file('%s_%s.png' % (graph_type, date_string))
    return os.path.join(GRAPH_DIR, file_name)

def get_date_list(created_data, closed_data, max_date):
    event_dates = set(created_data.iterkeys())
    event_dates.update(closed_data.iterkeys())
    min_date = min(event_dates)

    return [
        date.fromordinal(ordinal)
        for ordinal in xrange(min_date.toordinal(), max_date.toordinal() + 1)]

def graph_time_data(created_data, closed_data, title, file_name, y_label):
    today = date.fromordinal(date.today().toordinal())
    date_list = get_date_list(created_data, closed_data, today)

    first_work_date = None
    if closed_data:
        first_work_date = min(closed_data.iterkeys())

    created_series, closed_series = [], []
    cumulative_created, cumulative_closed = 0, 0
    for date_point in date_list:
        cumulative_created += created_data[date_point]
        cumulative_closed += closed_data[date_point]
        created_series.append((date_point, cumulative_created))
        closed_series.append((date_point, cumulative_closed))

    max_y_value = 1.1 * max(val for date_point, val in created_series)

    days_left, days_spent = None, None
    if first_work_date:
        days_spent = (today - first_work_date).days
        work_at_start = 0

        work_completed = closed_series[-1][1]
        if work_completed:
            total_work = created_series[-1][1]
            work_left = total_work - work_completed
            work_in_sample = work_completed - work_at_start
            work_per_day = work_in_sample / float(days_spent)
            days_left = int(math.ceil(work_left / work_per_day))

    plt.close('all')
    _, ax = plt.subplots(1)
    ax.fill_between(
        [x[0] for x in created_series],
        [x[1] for x in created_series],
        color='red')
    ax.fill_between(
        [x[0] for x in closed_series],
        [x[1] for x in closed_series],
        color='blue')
    ax.plot(
        [x[0] for x in created_series],
        [x[1] for x in created_series],
        label='%s Created' % y_label,
        color='black')
    ax.plot(
        [x[0] for x in closed_series],
        [x[1] for x in closed_series],
        label='%s Closed' % y_label,
        color='black')
    if days_spent and days_left:
        title += '\nApproximate Days Left: %i (%i-day sample)' % (days_left, days_spent)
    ax.set_title(title)
    ax.legend(loc='best')
    ax.set_ylabel(y_label)
    ax.xaxis.set_major_locator(MONTHS)
    ax.xaxis.set_major_formatter(MONTHS_FORMAT)
    ax.xaxis.set_minor_locator(WEEKS)
    ax.xaxis.set_minor_formatter(WEEKS_FORMAT)
    plt.ylim(0, max_y_value)
    plt.savefig(file_name, bbox_inches='tight')

def highlight_weekends(date_points, ax):
    today = date.today()
    saturdays = [
        date_point for date_point in date_points
        if date_point.weekday() == 5 and date_point != today]
    for saturday in saturdays:
        ax.axvspan(saturday, saturday + timedelta(days=1), facecolor='gray', edgecolor='none', alpha=.2)

def graph_daily_rates(project, closed_data, file_name):
    dev_days = devs_per_day(project['dev_days'])
    today = date.fromordinal(date.today().toordinal())
    date_list = get_date_list(dev_days, closed_data, today)


    MAX_DAYS_WITHOUT_DEVS = 3
    closed_series, devs_series = [], []
    rates = (ONE_WEEK * 4, ONE_WEEK * 2, ONE_WEEK)
    rate_series = {rate: [] for rate in rates}
    running_closed = {rate: deque(maxlen=rate) for rate in rates}
    running_devs = {rate: deque(maxlen=rate) for rate in rates}
    cum_closed_series = []
    cumulative_closed = 0
    for date_point in date_list:
        devs = dev_days.get(date_point, 0)
        closed = closed_data[date_point]

        cumulative_closed += closed
        cum_closed_series.append((date_point, cumulative_closed))

        for rate in rates:
            running_closed[rate].append(closed)
            running_devs[rate].append(devs)
        for rate in rates:
            if sum(list(running_devs[rate])[- MAX_DAYS_WITHOUT_DEVS:]):
                rate_series[rate].append((date_point, sum(running_closed[rate]) * 1.0 / sum(running_devs[rate])))
            else:
                rate_series[rate].append((date_point, 0))

        if closed_data[date_point]:
            closed_series.append((date_point, closed))
        if devs:
            devs_series.append((date_point, devs))

    final_rate = {rate: rate_series[rate][-1][1] for rate in rates}

    plt.close('all')
    _, ax = plt.subplots(1)

    ax.plot(
        [x[0] for x in cum_closed_series],
        [x[1] for x in cum_closed_series],
        label='Points Closed',
        color='blue',
        alpha=.8)
    ax.fill_between(
        [x[0] for x in cum_closed_series],
        [x[1] for x in cum_closed_series],
        color='blue',
        alpha=.3)
    max_y_points = 1.1 * max(val for date_point, val in cum_closed_series)
    ax.set_ylim(0, max_y_points)
    ax.set_ylabel('Cumulative Points Closed')

    ax_devs = ax.twinx()
    max_devs = max(val for date_point, val in devs_series)
    for count in range(max_devs, 1, -1):
        ax_devs.bar(
            [x[0] for x in devs_series],
            [count if x[1] >= count else 0 for x in devs_series],
            BAR_WIDTH,
            align='center',
            color='green', edgecolor='white',
            linewidth=.5)
    ax_devs.bar(
        [x[0] for x in devs_series],
        [1 for x in devs_series],
        BAR_WIDTH,
        align='center',
        label='Developers',
        color='green', edgecolor='white',
        linewidth=.5)

    max_y_devs = 5 * max_devs
    ax_devs.set_ylim(0, max_y_devs)
    ax_devs.set_yticklabels([])
    ax_devs.set_yticks([])

    ax_rate = ax.twinx()
    for rate, linestyle, linewidth in zip(rates, ('-', '--', ':'), (2, 1, 1)):
        ax_rate.plot(
            [x[0] for x in rate_series[rate]],
            [x[1] for x in rate_series[rate]],
            label='%i week: %.1f p/dd' % (rate / ONE_WEEK, final_rate[rate]),
            color='purple',
            linestyle=linestyle,
            linewidth=linewidth)
    max_y_rate = min(6, round(1.5 * max(val for date_point, val in chain(*rate_series.itervalues()))))
    ax_rate.set_ylim(0, max_y_rate)
    ax_rate.set_ylabel('Points / Dev-Day')

    ax.set_title('%s Points/Dev-Day' % project['name'])
    handles, labels = [
        reduce(lambda a, b: a + b, x)
        for x in zip(*(
            axis.get_legend_handles_labels()
            for axis in (ax, ax_devs, ax_rate)))]
    ax.legend(handles, labels, loc='upper center', fontsize='small')
    ax.xaxis.set_major_locator(MONTHS)
    ax.xaxis.set_major_formatter(MONTHS_FORMAT)
    ax.xaxis.set_minor_locator(WEEKS)
    ax.xaxis.set_minor_formatter(WEEKS_FORMAT)
    highlight_weekends(date_list, ax)
    plt.savefig(file_name, bbox_inches='tight')

# For graphing
def collect_time_data(created_data, closed_data):
    today = date.fromordinal(date.today().toordinal())
    date_list = get_date_list(created_data, closed_data, today)

    created_by_week, closed_by_week = defaultdict(int), defaultdict(int)
    cumulative_created = 0
    for date_point in date_list:
        weeks_ago = min(4, (today - date_point).days / ONE_WEEK)
        cumulative_created += created_data[date_point]
        created_by_week[weeks_ago] += created_data[date_point]
        closed_by_week[weeks_ago] += closed_data[date_point]

    new_total_issues = cumulative_created
    new_issues = created_by_week[0]
    old_total_issues = new_total_issues - new_issues

    sections = defaultdict(list)
    cumulative = 0
    for week in xrange(4, -1, -1):
        if old_total_issues:
            cumulative += round(100.0 * closed_by_week[week] / old_total_issues)
        sections[week].append(cumulative)
    remain = 100
    sections[-1].append(remain)
    sections[5].append(0.0)
    if old_total_issues:
        new = round(100.0 * new_total_issues / old_total_issues)
    else:
        sections[0] = round(100.0 * closed_by_week[0] / new_total_issues)
        new = 100 - sections[0]
    sections[-2].append(new)

    return sections

def graph_projects(all_sections, file_name):
    plt.close('all')
    _, ax = plt.subplots(1)
    for index, project_name in enumerate(sorted(all_sections.iterkeys())):
        sections = all_sections[project_name]
        plot = {}
        for week in xrange(-2, 6):
            plot[week] = plt.bar((index,), sections[week], BAR_WIDTH, color=GRAPH_COLORS[week], edgecolor='white', linewidth=.5)

    plt.grid(which='major', axis='y', linestyle='solid', color='#e9e9e9')
    plt.xticks([x + BAR_WIDTH / 2 for x in range(len(all_sections))], sorted(all_sections.iterkeys()))
    plt.tick_params(axis='x', which='both', bottom='off', top='off')
    plt.tick_params(axis='y', which='both', left='off', right='off', labelleft='off')
    xmin, xmax = plt.xlim()
    plt.xlim([xmin - (BAR_WIDTH / 2), xmax])
#    plt.ylim(0, 200)

    loc = plticker.MultipleLocator(base=GRID_WIDTH)
    ax.yaxis.set_major_locator(loc)
    ax.axhline(y=100, xmin=0, xmax=1, color='black', linestyle='dashed', linewidth=2)
    ax.set_axisbelow(True)

    plt.savefig(file_name, bbox_inches='tight')


def predict_completion(project, issues):
    project_name = project['name']
    print '\nPROJECT: %s' % project_name

    if not issues:
        print '*** NO ISSUES FOUND'
        return
    if 'dev_days' in project:
        max_dev_week = max(project['dev_days'].iterkeys())
        if (date.today() - max_dev_week).days > 7:
            print '*** DID YOU FORGET TO UPDATE DEV DAYS FOR %s THIS WEEK?' % project_name

        dev_days = sum(
            sum(int(day) for day in week.split(','))
            for week in project['dev_days'].itervalues())
        print '%i dev-days so far' % dev_days
    else:
        dev_days = 0
        print '0 dev-days recorded'
    print '-' * 20

    for use_story_points in (True, False):
        units = 'points' if use_story_points else 'stories'
        created_by_date, closed_by_date = created_and_closed_by_date(
            issues, HIGH_P, use_story_points=use_story_points)
        num_created = sum(created_by_date.itervalues())
        num_closed = sum(closed_by_date.itervalues())
        num_left = num_created - num_closed

        if dev_days:
            rate = 1.0 * num_closed / dev_days

        print '%i %s closed' % (num_closed, units)
        print '%i %s left' % (num_left, units)
        if num_closed:
            days_left = num_left / rate
            print '%.1f %s per dev-day' % (rate, units)
            print 'BY %s: ~%i dev days left (~%i dev weeks)' % (units.upper(), round(days_left), round(days_left / 5))
        else:
            print 'BY %s: Cannot prediction completion date yet' % units.upper()

def main():
    args = collect_options()
    jira = JIRA(args.config_file)
    all_projects = load_projects(args.projects_file)
    if args.all_reports:
        projects = all_projects
        graph_type = None
    else:
        projects = prompt_for_projects(all_projects)
        graph_type = prompt_for_graph_type()

    all_sections = {}
    for project in projects:
        project_name = project['name']
        issues = jira.query(project['query'], args.use_cache)
        if not issues:
            continue

        issues = [
            i for i in issues
            if i['fields']['issuetype']['name'] != 'Epic']

        if not graph_type or graph_type == 'completion':
            predict_completion(project, issues)

        created_by_date, closed_by_date = created_and_closed_by_date(issues, HIGH_P)
        num_created = sum(created_by_date.itervalues())
        num_closed = sum(closed_by_date.itervalues())
        percent_complete = round(100.0 * num_closed / num_created)

        if project.get('done'):
            sections = defaultdict(list, {0: [0.0], 1: [0.0], 2: [0.0], 3: [0.0], 4: [0.0], 5: [100.0], -2: [0.0], -1: [0.0]})
        else:
            sections = collect_time_data(created_by_date, closed_by_date)
        all_sections[project_name] = sections

        if not graph_type or graph_type == 'points':
            if 'dev_days' in project:
                _, points_closed_by_date = created_and_closed_by_date(issues, HIGH_P, use_story_points=True)
                graph_daily_rates(
                    project,
                    points_closed_by_date,
                    graph_file('%s daily rates' % project_name))

        if not graph_type or graph_type == 'issues':
            graph_time_data(
                created_by_date,
                closed_by_date,
                '%s Issues >= P2 (%i%% Complete)' % (project_name, percent_complete),
                graph_file('%s issues over time' % project_name),
                'Issues')

    if not graph_type or graph_type == 'projects':
        graph_projects(all_sections, graph_file('all projects'))

main()
