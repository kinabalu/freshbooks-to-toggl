import argparse
import requests
import sys
import json

import datetime
# from tzlocal import get_localzone
from pytz import timezone

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

    def __init__(self, api_token):
        self.api_token = api_token

    def _make_url(self, section='time_entries', params={}):
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

    def get_time_entry_pagecount(self, project_id, date_from, date_to, task_id=None):
        """
        Returns the page count of time entries so we can iterate if needed
        """
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

        return time_entries_response.time_entries.attrib['pages']

    def get_time_entries(self, project_id, date_from, date_to, task_id=None):
        """
        Pull back time entries from Freshbooks.  Has a default of 25 entries per
        page.
        """

        page_count = int(self.get_time_entry_pagecount(project_id, date_from, date_to, task_id))

        print('Page Count: %d' % page_count)
        time_entries = []

        for x in range(1, page_count+1):
            time_entries_response = self.c.time_entry.list(
                project_id=project_id,
                date_from=date_from,
                date_to=date_to,
                page=x
            ) if task_id is None else self.c.time_entry.list(
                project_id=project_id,
                task_id=task_id,
                date_from=date_from,
                date_to=date_to,
                page=x
            )

            for time_entry in time_entries_response.time_entries.time_entry:
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

        print('Number of time entries: %d' % (len(time_entries)))
        return time_entries


class FreshbooksToToggl(object):

    def __init__(self):
        self.freshbooks = Freshbooks()
        self.toggl = TogglAPI(config.TOGGL_API_TOKEN)
        self.pacific = timezone(config.TIMEZONE)

    def _convert_hours_to_seconds(self, hours):
        return float(hours) * 60 * 60

    def _freshbooks_entry_as_dict(self, freshbooks_entry):
        date_split = freshbooks_entry['date'].split('-')
        start_date = datetime.datetime(int(date_split[0]), int(date_split[1]), int(date_split[2]), 0, 0, 0, 0, tzinfo=self.pacific)
        duration = self._convert_hours_to_seconds(freshbooks_entry['hours'])
        project_id = None

        task_id = str(freshbooks_entry['task_id'])
        if task_id in config.F_TO_T_MAPPING:
            project_id = config.F_TO_T_MAPPING[task_id]
        else:
            return None

        return {
            "billed": freshbooks_entry['billed'],
            "start_date": start_date,
            "duration": duration,
            "project_id": project_id,
            "description": freshbooks_entry['notes']
        }

    def list_entries(self, start_date, end_date, freshbooks_project_id):
        freshbooks_time_entries = self.freshbooks.get_time_entries(
            project_id=freshbooks_project_id,
            date_from=start_date,
            date_to=end_date
        )
        pprint(freshbooks_time_entries, indent=4)

    def list_toggl_tasks(self, project_id):
        task_entries = self.toggl.get_project_tasks(project_id)
        pprint(task_entries, indent=4)

    def sync(self, start_date, end_date, freshbooks_project_id, create_entries):
        freshbooks_time_entries = self.freshbooks.get_time_entries(
            project_id=freshbooks_project_id,
            date_from=start_date,
            date_to=end_date
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

        for fbe in freshbooks_time_entries:

            data = self._freshbooks_entry_as_dict(fbe)
            # print("Data is: %s" % data)

            pprint(data)
            if data is not None and create_entries:
                self.toggl.create_time_entry(
                    project_id=data['project_id'],
                    description=data['description'],
                    start_date=data['start_date'],
                    duration=data['duration']
                )
        # workspace_projects = toggl.get_workspace_projects(X)
        # print json.dumps(workspace_projects, indent=4, sort_keys=True)
        # listinvoices = Freshbooks()

        # if args.listinvoices:
        #     sbr.sync()


def main():
    parser = argparse.ArgumentParser(prog='freshbooks-to-toggl')

    parser.add_argument(
        "--listinvoices",
        dest="listinvoices",
        action="store_true"
    )

    parser.add_argument(
        "--from",
        dest="start_date",
        type=str,
        help="Start date of the form YYYY-MM-DD"
    )

    parser.add_argument(
        "--to",
        dest="end_date",
        type=str,
        help="End date of the form YYYY-MM-DD"
    )

    parser.add_argument(
        "--project_id",
        dest="project_id",
        type=int,
        help="Freshbooks Project ID"
    )

    parser.add_argument(
        "--list_entries",
        dest="list_entries",
        action="store_true"
    )

    parser.add_argument(
        "--toggl-tasks",
        dest="toggl_tasks",
        action="store_true"
    )

    parser.add_argument(
        "--toggl-project-id",
        dest="toggl_project_id",
        type=int,
        help="Toggl Project ID"
    )

    parser.add_argument(
        "--sync",
        dest="sync",
        action="store_true"
    )

    args = parser.parse_args()

    if args.sync:
        print('Retrieving and posting time entries from: %s to %s' % (args.start_date, args.end_date,))
        fb_to_toggl = FreshbooksToToggl()
        fb_to_toggl.sync(args.start_date, args.end_date, args.project_id, create_entries=True)
    elif args.list_entries:
        fb_to_toggl = FreshbooksToToggl()
        fb_to_toggl.list_entries(args.start_date, args.end_date, args.project_id)
    elif args.toggl_tasks:
        fb_to_toggl = FreshbooksToToggl()
        fb_to_toggl.list_toggl_tasks(args.toggl_project_id)


if __name__ == '__main__':
    main()
