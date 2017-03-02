from fabric.operations import local, sudo
from fabric.api import env, settings
from time import sleep
from time import time
from datetime import datetime
import re
import random
from multiprocessing import Process, Array, Manager
import servicespecific


################
# FABRIC TASKS #
################

# Main application flow
def unleash_chaos():
    # Command-line arguments
    duration_in_minutes = env.duration
    inventory_file = env.inventory_file
    scenario_file = env.scenario_file

    dry_run = False
    if env.dry_run is not None and env.dry_run.lower() == "true":
        dry_run = True

    # Initializations
    chaos_tasks = parse_scenario_file(scenario_file)
    chaos_task_restored = init_thread_safe_chaos_task_statuses(chaos_tasks)
    current_host_per_task = init_thread_safe_current_host_map()

    # Execute chaos tasks in parallel and terminate them when the execution time has passed.
    log_message("About to unleash chaos for at least %s minutes" % duration_in_minutes)
    start_time = time()
    duration_in_minutes_int = int(duration_in_minutes)
    duration_in_seconds = duration_in_minutes_int if dry_run is True else duration_in_minutes_int * 60
    task_processes = execute_chaos_tasks_in_parallel(chaos_task_restored, chaos_tasks, inventory_file, current_host_per_task, dry_run)
    terminate_if_execution_time_has_passed(chaos_task_restored, duration_in_seconds, start_time, task_processes, dry_run)
    log_message("Done, no more chaos for now!")


# Reverts chaos on all hosts for all groups in a scenario file.
def revert_chaos():
    # Command-line arguments
    inventory_file = env.inventory_file
    scenario_file = env.scenario_file
    current_host_per_task = init_thread_safe_current_host_map()

    # Initializations
    chaos_tasks = parse_scenario_file(scenario_file)
    for task_number, chaos_task in enumerate(chaos_tasks):
        group = chaos_task[0]
        service_name = chaos_task[1]
        monkey = chaos_task[2]
        hosts = ansible_get_hosts_for_group(inventory_file, group)
        for host in hosts:
            current_host_per_task[task_number] = host
            revert_chaos_for_one_host(current_host_per_task, monkey, service_name, task_number, False)


####################
# HELPER FUNCTIONS #
####################

# Thread-safe character array that's shared between processes. "t" and "f" for true and false.
def init_thread_safe_chaos_task_statuses(chaos_tasks):
    chaos_task_restored = Array('c', len(chaos_tasks))
    for i in range(len(chaos_task_restored)):
        chaos_task_restored[i] = "f"
    return chaos_task_restored


# Thread-safe dict that acts as map with task number as key and the current randomly picked host.
def init_thread_safe_current_host_map():
    return Manager().dict()


# Main loop that checks if execution time has passed an in that case terminates the chaos task processes when they have been restored.
def terminate_if_execution_time_has_passed(chaos_task_restored, duration_in_seconds, start_time, task_processes, dry_run):
    while True:
        sleep_minutes(1, dry_run)
        time_passed_in_seconds = time() - start_time
        if time_passed_in_seconds >= duration_in_seconds:
            for i in range(len(chaos_task_restored)):
                if chaos_task_restored[i] == "t" and task_processes[i].is_alive():
                    log_message("Terminating task %i" % i)
                    task_processes[i].terminate()

            # If all chaos tasks have been restored, break out of the infinite loop.
            if chaos_task_restored[:] == "t" * len(chaos_task_restored):
                break


# Executes all chaos tasks in one new thread each and save it in an array.
def execute_chaos_tasks_in_parallel(chaos_task_restored, chaos_tasks, inventory_file, current_host_per_task, dry_run):
    task_processes = []

    for task_number, chaos_task in enumerate(chaos_tasks):
        task_process = Process(target=execute_chaos_task, args=(task_number, chaos_task, inventory_file, chaos_task_restored, current_host_per_task, dry_run))
        task_process.start()
        task_processes.append(task_process)

    return task_processes


# Executes one cycle of a chaos task: 1) Sleep 2) Unleash monkey 3) Sleep 4) Revert chaos
def execute_chaos_task(task_number, chaos_task, inventory_file, chaos_task_restored, current_host_per_task, dry_run):
    group = chaos_task[0]
    service_name = chaos_task[1]
    monkey = chaos_task[2]
    chaos_active_time_interval = chaos_task[3]
    chaos_inactive_time_interval = chaos_task[4]
    misc_settings = chaos_task[5]

    log_task_and_group_message(task_number, group, "Executing group.")
    hosts = ansible_get_hosts_for_group(inventory_file, group)
    log_task_and_group_message(task_number, group, "hosts: %s" % ", ".join(str(host) for host in hosts))

    while True:
        chaos_task_restored[task_number] = "t"
        current_host_per_task[task_number] = random.choice(hosts)
        chaos_inactive_time = get_random_number_in_interval(chaos_inactive_time_interval)
        chaos_active_time = get_random_number_in_interval(chaos_active_time_interval)

        # Step 1 (Chaos inactive)
        log_task_and_group_message(task_number, group, "Taking a break for %i minute(s), sleeping..." % chaos_inactive_time)
        sleep_minutes(chaos_inactive_time, dry_run)

        # Step 2 (Unleash monkey)
        chaos_task_restored[task_number] = "f"

        if monkey == "chaos-monkey":
            log_task_and_group_message(task_number, group, "Task %i is about to unleash Chaos monkey (%s) on host %s" % (task_number, misc_settings, current_host_per_task[task_number]))
            if misc_settings == "kill":
                kill_service(task_number, current_host_per_task, service_name, dry_run)
            elif misc_settings == "stop":
                stop_service(task_number, current_host_per_task, service_name, dry_run)
        elif monkey == "clog-monkey":
            log_task_and_group_message(task_number, group, "Task %i is about to unleash Clog monkey on host %s" % (task_number, current_host_per_task[task_number]))
            clog_network(task_number, current_host_per_task, misc_settings, dry_run)

        # Step 3 (Chaos active)
        log_task_and_group_message(task_number, group, "Taking a break for %i minute(s), eating a banana..." % chaos_active_time)
        sleep_minutes(chaos_active_time, dry_run)

        # Step 4 (Revert chaos)
        revert_chaos_for_one_host(current_host_per_task, monkey, service_name, task_number, dry_run)


def revert_chaos_for_one_host(current_host_per_task, monkey, service_name, task_number, dry_run):
    if monkey == "chaos-monkey":
        start_service(task_number, current_host_per_task, service_name, dry_run)
    elif monkey == "clog-monkey":
        unclog_network(task_number, current_host_per_task, dry_run)


def sleep_minutes(minutes, dry_run):
    # If it's a dry run, pretend that one second is one minute to make it run faster.
    seconds_to_sleep = minutes if dry_run is True else minutes * 60
    sleep(seconds_to_sleep)


def ansible_get_hosts_for_group(inventory_file, group):
    log_message("Getting %s from %s..." % (group, inventory_file))
    hosts = local("ansible %s -i %s --list-hosts" % (group, inventory_file), capture=True).split("\n")

    for index in range(len(hosts)):
        hosts[index] = hosts[index].strip(" ")

    return hosts


def log_message(message):
    print "[%s] %s" % (str(datetime.now()), message)


def log_task_and_group_message(task_number, group, message):
    print "[%s Task %i %s] %s" % (str(datetime.now()), task_number, group, message)


def log_action(monkey_name, include_hosts, message):
    print "[%s %s %s] %s" % (str(datetime.now()), monkey_name, include_hosts, message)


def log_dry_run_sudo_command(command):
    print "[%s DRY RUN] sudo %s" % (str(datetime.now()), command)


def parse_scenario_file(scenario_file):
    chaos_tasks = []

    with open(scenario_file) as opened_file:
        lines = opened_file.readlines()
        log_message("Chaos tasks in scenario file:")
        for line in lines:
            # Ignore empty lines and comments (lines that start with "#").
            if not (line.rstrip('\n') == "" or line.startswith("#")):
                # Split on whitespace and remove carriage returns.
                print line
                line_split = re.split(r' +', line.rstrip("\n"))
                chaos_tasks.append(line_split)

    return chaos_tasks


def get_random_number_in_interval(interval):
    min_and_max = interval.split("-")
    return random.randint(int(min_and_max[0]), int(min_and_max[1]))


def parse_clog_monkey_misc_settings(misc_settings):
    def to_int(s): return int(s)
    (delay, delay_variance, loss) = tuple(misc_settings.split(","))
    delay_interval = tuple(map(to_int, re.split(r'-+', delay.rstrip("ms"))))
    delay_variance = to_int(delay_variance.replace("ms", ""))
    loss_interval = tuple(map(to_int, re.split(r'-+', loss.rstrip("%"))))
    return delay_interval, delay_variance, loss_interval


################
# CHAOS MONKEY #
################

def kill_service(task_number, current_host_per_task, service_name, dry_run):
    log_message("Task %i, host %s" % (task_number, current_host_per_task[task_number]))
    with settings(host_string=current_host_per_task[task_number], warn_only=True):
        pid = "dummy_pid" if dry_run is True else servicespecific.get_pid(service_name)
        log_action("CHAOS MONKEY", current_host_per_task[task_number], "Killing %s with id %s..." % (service_name, pid))
        if pid is not None:
            execute_sudo_command("kill -9 %s" % pid, dry_run)
            log_action("CHAOS MONKEY", current_host_per_task[task_number], "%s with pid %s killed!" % (service_name, pid))
        else:
            log_action("CHAOS MONKEY", current_host_per_task[task_number], "Could not find pid for service %s. Doing nothing." % service_name)


def stop_service(task_number, current_host_per_task, service_name, dry_run):
    log_message("Task %i, host %s" % (task_number, current_host_per_task[task_number]))
    with settings(host_string=current_host_per_task[task_number], warn_only=True):
        execute_sudo_command("service %s stop" % service_name, dry_run)
        log_action("CHAOS MONKEY", current_host_per_task[task_number], "%s stopped!" % service_name)


###############
# CLOG MONKEY #
###############

def clog_network(task_number, current_host_per_task, misc_settings, dry_run):
    delay_interval, delay_variance, loss_interval = parse_clog_monkey_misc_settings(misc_settings)
    log_message("Task %i, host %s" % (task_number, current_host_per_task[task_number]))
    with settings(host_string=current_host_per_task[task_number], warn_only=True):
        log_action("CLOG MONKEY", current_host_per_task[task_number], "Clogging network...")
        execute_sudo_command("tc qdisc add dev eth0 root netem delay %ims %ims loss %i%%" % (random.randint(delay_interval[0], delay_interval[1]), delay_variance, random.randint(loss_interval[0], loss_interval[1])), dry_run)
        log_action("CLOG MONKEY", current_host_per_task[task_number], "Network clogged!")


##################
# JANITOR MONKEY #
##################

def start_service(task_number, current_host_per_task, service_name, dry_run):
    log_message("Task %i, host %s" % (task_number, current_host_per_task[task_number]))
    with settings(host_string=current_host_per_task[task_number], warn_only=True):
        execute_sudo_command(servicespecific.get_start_service_command(service_name), dry_run)
        log_action("JANITOR MONKEY", current_host_per_task[task_number], "%s started up!" % service_name)


def unclog_network(task_number, current_host_per_task, dry_run):
    log_message("Task %i, host %s" % (task_number, current_host_per_task[task_number]))
    with settings(host_string=current_host_per_task[task_number], warn_only=True):
        log_action("JANITOR MONKEY cleans up after CLOG MONKEY", current_host_per_task[task_number], "Unclogging network...")
        execute_sudo_command("tc qdisc del dev eth0 root netem", dry_run)
        log_action("CLOG MONKEY", current_host_per_task[task_number], "Network unclogged!")


def execute_sudo_command(command, dry_run):
    if dry_run is True:
        log_dry_run_sudo_command(command)
    else:
        sudo(command)
