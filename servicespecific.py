# file  -- servicespecific.py --


from fabric.operations import sudo
from fabric.api import env
import re
from interface import Interface, implements


###################
# "API" FUNCTIONS #
###################
def get_pid(service_name):
    return get_server_specific_instance(service_name).get_pid()


def get_start_service_command(service_name):
    return get_server_specific_instance(service_name).start_service_command()


# Factory like function that returns different instances depending on the service name.
def get_server_specific_instance(service_name):

    # As there is only one server-specific implementation, just return an instance of it.
    # After adding more implementations service_name can be used to determine which instance to return.
    server_specific_instance = DropwizardService(service_name)

    return server_specific_instance


# Base class that holds the service name.
class ServiceSpecificBase:
    def __init__(self, service_name):
        self.service_name = service_name


# Server specific interface that defines which functions need to be implemented.
class ServiceSpecific(Interface):
    def get_pid(self):
        pass

    def start_service_command(self):
        pass


###################################
# SERVER SPECIFIC IMPLEMENTATIONS #
###################################
class DropwizardService(ServiceSpecificBase, implements(ServiceSpecific)):
    def get_pid(self):
        # Example, extracts the pids from the following:
        # sudo service the-service-name status
        # the-service-name start/running, process 26591
        try:
            result = int(sudo("service %s status" % self.service_name).split(" ").pop())
        except ValueError:
            result = None
        return result

    def start_service_command(self):
        return "service %s start" % self.service_name
