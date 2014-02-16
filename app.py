import argparse
import requests
import sys
import json

import datetime
# from tzlocal import get_localzone
from pytz import timezone
import pytz

from urllib import urlencode
from requests.auth import HTTPBasicAuth
from refreshbooks import api

from pprint import pprint

try:
    import config
except ImportError:
    print("Config file config.py.tmpl needs to be copied over to config.py")
    sys.exit(1)


class TogglAPI(object):
    """
    A wrapper for the Toggl API

    https://github.com/toggl/toggl_api_docs/blob/master/toggl_api.md
    """

    def __init__(self, api_token, timezone):
        self.api_token = api_token
        self.timezone = timezone

    def _make_url(self, section='time_entries', params={}):
        """Constructs and returns an api url to call with the section of the API to be called
        and parameters defined by key/pair values in the paramas dict.
        Default section is "time_entries" which evaluates to "time_entries.json"

        >>> t = TogglAPI('_SECRET_TOGGLE_API_TOKEN_')
        >>> t._make_url(section='time_entries', params = {})
        'https://www.toggl.com/api/v8/time_entries'

        >>> t = TogglAPI('_SECRET_TOGGLE_API_TOKEN_')
        >>> t._make_url(section='time_entries', params = {'start_date' : '2010-02-05T15:42:46+02:00', 'end_date' : '2010-02-12T15:42:46+02:00'})
        'https://www.toggl.com/api/v8/time_entries?start_date=2010-02-05T15%3A42%3A46%2B02%3A00%2B02%3A00&end_date=2010-02-12T15%3A42%3A46%2B02%3A00%2B02%3A00'
        """

        url = 'https://www.toggl.com/api/v8/{}'.format(section)
        if len(params) > 0:
            url = url + '?{}'.format(urlencode(params))
        return url

    def _query(self, url, method, payload=None):
        """Performs the actual call to Toggl API"""

        url = url
        headers = {'content-type': 'application/json'}

        if method == 'GET':
            return requests.get(url, headers=headers, auth=HTTPBasicAuth(self.api_token, 'api_token'))
        elif method == 'POST':
            return requests.post(url, headers=headers, auth=HTTPBasicAuth(self.api_token, 'api_token'), data=json.dumps(payload))
        else:
            raise ValueError('Undefined HTTP method "{}"'.format(method))

    def get_workspaces(self):
        """Get workspaces for user"""

        url = self._make_url(section='workspaces')
        r = self._query(url=url, method='GET')
        return r.json()

    def get_workspace_clients(self, wid):
        """Get workspace clients"""
        # url = self._make_url(section='workspaces', params=)
        r = self._query(url=url, method='GET')
        return r.json()

    ## Time Entry functions
    def get_time_entries(self, start_date, end_date):
        """Get Time Entries JSON object from Toggl"""

        url = self._make_url(section='time_entries', params={'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()})
        r = self._query(url=url, method='GET')
        return r.json()

    def get_hours_tracked(self, start_date, end_date):
        """Count the total tracked hours excluding any RUNNING real time tracked time entries"""
        time_entries = self.get_time_entries(start_date=start_date.isoformat(), end_date=end_date.isoformat())

        if time_entries is None:
            return 0

        total_seconds_tracked = sum(max(entry['duration'], 0) for entry in time_entries)

        return (total_seconds_tracked / 60.0) / 60.0

    def get_project_tasks(self, project_id):
        """Get project tasks from Toggl"""
        url = 'https://www.toggl.com/api/v8/projects/%d/tasks' % (project_id,)

        r = self._query(url=url, method='GET')
        return r.json()

    def get_workspace_projects(self, workspace_id):
        """Get workspace projects from Toggl"""
        url = 'https://www.toggl.com/api/v8/workspaces/%d/projects' % (workspace_id,)

        r = self._query(url=url, method='GET')
        return r.json()

    def create_time_entry(self, project_id, description, start_date, duration, created_with='Freshbooks to Toggl'):
        # do we convert duration to something usable by Toggl or assume that it will be passed in as seconds?
        data = {
            "time_entry": {
                "description": description,
                "pid": project_id,
                "start": start_date.isoformat(),
                "duration": duration,
                "created_with": created_with
            }
        }
        url = self._make_url(section='time_entries')
        r = self._query(url=url, method='POST', payload=data)


class Freshbooks(object):
    """
    Freshbooks API wrapper

    using the following code: https://pypi.python.org/pypi/refreshbooks/
    """
    def __init__(self):
        self.c = api.TokenClient(
            config.FRESHBOOKS_SITE_DOMAIN,
            config.FRESHBOOKS_API_TOKEN,
            user_agent='Freshbooks to Toggl Sync'
        )

    def get_client_list(self):
        client_response = self.c.client.list()

        for client in client_response.clients.client:
            print('%s [%d]' % (client.organization, client.client_id))

    def get_project_list(self):
        project_response = self.c.project.list()

        project_entries = []
        for project in project_response.projects.project:
            project_entries.append({
                'id': project.project_id,
                'name': project.name,
                'description': project.description,
                'rate': project.rate,
                'bill_method': project.bill_method,
                'client_id': project.client_id
            })
        return project_entries

    def get_task_list(self, project_id=None):
        task_response = self.c.task.list() if project_id is None else self.c.task.list(project_id=project_id)

        task_entries = []
        for task in task_response.tasks.task:
            task_entries.append({
                'id': task.task_id,
                'name': task.name,
                'description': task.description,
                'billable': (True if task.billable is 1 else False),
                'rate': task.rate
            })
        return task_entries

    def get_time_entries(self, project_id, date_from, date_to, task_id=None):
        time_entries_response = self.c.time_entry.list(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to
        ) if task_id is None else self.c.time_entry.list(
            project_id=project_id,
            task_id=task_id,
            date_from=date_from,
            date_to=date_to
        )

        time_entries = []
        for time_entry in time_entries_response.time_entries.time_entry:
            print(type(time_entry.hours))
            time_entries.append({
                'id': time_entry.time_entry_id,
                'staff_id': time_entry.staff_id,
                'project_id': time_entry.project_id,
                'task_id': time_entry.task_id,
                'hours': time_entry.hours.pyval,
                'date': time_entry.date.text,
                'notes': time_entry.notes.text,
                'billed': (True if time_entry.billed is 1 else False)
            })
        return time_entries


def main():
    parser = argparse.ArgumentParser(prog='freshbooks-to-toggl')

    parser.add_argument(
        "--listinvoices",
        dest="listinvoices",
        action="store_true"
    )

    args = parser.parse_args()

    freshbooks = Freshbooks()
    toggl = TogglAPI(config.TOGGL_API_TOKEN, '')

    freshbooks_time_entries = freshbooks.get_time_entries(
        project_id=58,
        date_from='2014-02-01',
        date_to='2014-02-15'
    )
    pprint(freshbooks_time_entries, indent=4)
    """
    workspace_id=362157
    # project_list = freshbooks.get_project_list()
    # pprint(project_list, indent=4)
    # task_list = freshbooks.get_task_list(project_id=58)
    # pprint(task_list, indent=4)

    toggl_time_entries = toggl.get_time_entries(
        datetime.datetime(2014, 2, 1, 0, 0, 0, 0, tzinfo=pytz.utc),
        datetime.datetime(2014, 2, 15, 0, 0, 0, 0, tzinfo=pytz.utc)
    )
    pprint(toggl_time_entries, indent=4)
    """

    # toggl.create_time_entry(3118552, 'Testing from API caller', datetime.datetime(2014, 2, 2, 0, 0, 0, 0, tzinfo=pytz.utc), 1200)
    #    def create_time_entry(self, project_id, description, start_date, duration, created_with='Freshbooks to Toggl'):

    # "Websites - Infrastructure" = 3118555  === Freshbooks = 5
    # "Websites - Project Management & Meetings" = 3118552 === Freshbooks 2, 3
    # "Websites - Care & Feeding" = 3118550 === Freshbooks 4

    pacific = timezone('US/Pacific')
    for fbe in freshbooks_time_entries:
        duration = float(fbe['hours']) * 60 * 60          # convert the hours in Freshbooks to a seconds-based duration
        project_id = None

        if fbe['task_id'] == 5:
            project_id = 3118555
        elif fbe['task_id'] == 2 or fbe['task_id'] == 3:
            project_id = 3118552
        elif fbe['task_id'] == 4:
            project_id = 3118550

        if project_id is None:
            continue

        date_split = fbe['date'].split("-")
        start_date = datetime.datetime(int(date_split[0]), int(date_split[1]), int(date_split[2]), 0, 0, 0, 0, tzinfo=pacific)

        print('Project ID: %s, Description: %s, Start Date: %s, Duration: %s' % (project_id, fbe['notes'], start_date, duration))
        toggl.create_time_entry(
            project_id=project_id,
            description=fbe['notes'],
            start_date=start_date,
            duration=duration
        )
    # workspace_projects = toggl.get_workspace_projects(362157)
    # print json.dumps(workspace_projects, indent=4, sort_keys=True)
    # listinvoices = Freshbooks()

    # if args.listinvoices:
    #     sbr.sync()


if __name__ == '__main__':
    main()