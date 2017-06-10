#!/usr/bin/python

# The Python `requests` library is required to run this script.
# http://docs.python-requests.org/en/master/
#
# To install:
#     `sudo pip install requests`


from ConfigParser import ConfigParser
import httplib
import json
import os
import re
from sha import sha
import urllib

import requests


VERBOSE = False


def print_verbose(string):
    if VERBOSE:
        print(string)


class ContainsEverything(object):
    def __contains__(self, value):
        return True


class JIRA(object):
    SEARCH_API = 'https://%s/rest/api/2/search?maxResults=-1&jql='
    BAD_HOSTNAME = re.compile('https?:\/\/')

    def __init__(self, config_file):
        config = ConfigParser()
        config.read(config_file)

        self.hostname = config.get('server', 'hostname')
        assert not self.BAD_HOSTNAME.match(self.hostname), 'Hostname in config should not start with "http"'
        self.search_api = self.SEARCH_API % self.hostname

        self.username = config.get('user', 'username')
        self.password = config.get('user', 'password')

        self.cache_directory = config.get('cache', 'directory')

        self.high_priorities = config.get('jira', 'white_list_priorities') or ContainsEverything()
        self.done_statuses = config.get('jira', 'done_statuses')
        self.story_points_field = config.get('jira', 'story_points_field')

        self.session = requests.session()

    def cache_file(self, query):
        if self.cache_directory:
            hash_value = sha(query).hexdigest()
            file_name = '%s.cached.json' % hash_value
            return os.path.join(self.cache_directory, file_name)

    def get_with_auth(self, url):
        result = self.session.get(url, auth=(self.username, self.password))        
        assert result.status_code == httplib.OK, 'URL %s got status: %s\n%s' % (url, result.status_code, result.content)
        return result

    def query(self, query, use_cache=False):
        cache_file = self.cache_file(query)
        if use_cache and os.path.isfile(cache_file):
            print('FETCHING FROM CACHE: %s' % query)
            with open(cache_file, 'r') as f:
                raw_json = f.read()
                issues = json.loads(raw_json)
        else:
            print_verbose('QUERYING JIRA: %s' % query)
            query_url = self.search_api + urllib.quote(query)
            result = self.get_with_auth(query_url)
            data = result.json()
            try:
                issues = data['issues']
                with open(cache_file, 'w') as f:
                    f.write(json.dumps(issues))
            except:
                print('ERRORS with URL: %s' % query_url)
                print('\n'.join(data['errorMessages']))
                raise
        return issues
