# Chaos chapter

Inspired by Netflix's Simian Army (https://github.com/Netflix/SimianArmy), monkeys inject different kinds of chaos into a system.

Clog monkey is inspired by this article from PagerDuty:
https://www.pagerduty.com/blog/failure-friday-at-pagerduty/


## How it works

It reads host names from an Ansible inventory file and chaos tasks from a scenario file.

Each chaos task is then executed in parallel. A chaos task is executed repeatedly where each cycle in the loop consists of 4 steps:
1) Sleep ("Chaos inactive time" in the scenario file).
2) Unleash chaos. What happens depends on the what monkey it is.
3) Sleep ("Chaos active time" in the scenario file).
4) Restore.

This is repeated for the duration specified as an input to the Fabric script. Tasks are not terminated immediately but rather when a cycle has finished so that
the state is restored. This means that the program will run for AT LEAST the duration specified.


## Scenario

A scenario consist of a list of chaos tasks where one chaos task has the following settings:

Ansible server group:
Name of the server group on the Ansible inventory

Service:
Name of the service

Monkey:
The monkey to associate this task with

Chaos active time:
Time in minutes (should be > 0) to sleep after a chaos task has been activated

Chaos inactive time:
Time in minutes (should be > 0) to sleep before a chaos task has been activated

Misc:
Monkey specific settings


## Chapter members

### Chaos monkey

Similar to the one from Netflix with the same name (https://github.com/netflix/chaosmonkey).
Misc settings can be either "stop" or "kill" which makes chaos monkey either stop or kill (as in "kill -9") the service.


### Clog monkey

Adds delay and packet loss to network traffic. 

Example of Misc settings in scenario file:

`
300-600ms,100ms,2-7%
`

This might result in the following command being executed (for the ranges values are picked randomly within the ranges specified):

`
tc qdisc add dev eth0 root netem delay 505ms 100ms loss 3%
`

In this case the network traffic is delayed by 505 +- 100ms and there is a packet loss of 3%. 



### Janitor monkey

Restore whatever chaos has been injected.

For example, clean up after
* Chaos monkey means starting up a service
* Clog monkey means removing the network delay and packet loss simulation:

`sudo tc qdisc del dev eth0 root netem` 


## Example usage

Inject chaos according to a given scenario for at least 60 minutes using hosts in the given inventory file:

`
fab unleash_chaos --set duration=60,scenario_file=[path_to_scenario_file],inventory_file=[path_to_inventory_file]
`

Chaos can be reverted for all hosts in all groups like this:
 
`
fab revert_chaos --set scenario_file=[path_to_scenario_file],inventory_file=[path_to_inventory_file]
`

If something fails, for example if it tries to startup a service that is already started it will just log an error and continue.


## Dry run

By setting the dry_run flag to true you can try out your scenario before running it for real. To make make it run faster one minute in this case is one second instead.
It will print out all the tasks it WOULD execute so you can verify that your scenario results in the expected outcome.
The following command can be executed using the provided example files:

`
fab unleash_chaos --set duration=10,scenario_file=examples/example_scenario,inventory_file=examples/example_inventory,dry_run=true
`


## Pre-requisites

Python (https://www.python.org/), Fabric (http://www.fabfile.org/) and Ansible (https://www.ansible.com/) need to be installed.

Developed and tested with Python 2.7.13, Fabric 1.13.1 (with Paramiko 2.1.1) and Ansible 1.9.6.
