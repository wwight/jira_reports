JIRA Reports Scripts
======

This makes pretty graphs for JIRA status updates.

### Setup

Install dependencies
```
sudo pip install requests
sudo pip install matplotlib
sudo pip install pyyaml
```

```
cp example_jira.cfg jira.cfg
```

Fill in your JIRA username / password. 

```
cp example_projects.yml projects.yml
```

Fill in your project data.

### usage

To run:

```
./project_report.py jira.cfg projects.yml
```

The output files will be in `graphs/`

### To Do List
- Split time left per P-value OR per Epic