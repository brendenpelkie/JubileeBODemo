# this module should handle taking things like "add 5ml of red solution to well A1" and convert that to 'move to XYZ, 'extrude' 5 ml" which will be passed to the jubilee controller

# jubilee generic tool class - no external tool required

# jubilee generic tool class - needs an external tool (ie camera vi rpi)

# for demo: write all of this in one class that does all the functionality. refactor to abstract better once we are doing our own API

#heavilyt copied from sonication_station Joshua Vasquez
import json
import time
from functools import wraps
from .jubilee_controller import JubileeMotionController, MachineStateError


def protocol_method(func):
    """mark a function as useable in protocols"""
    func.is_protocol_method = True
    return func

def requires_safe_z(func):
    #@wraps(func) We should be cutting out inpromptu so shouldn't need this
    """
    decorate functions to require a z clearance check
    """
    def safe_z_check(self, *args, **kwargs):
        if self.safe_z is None:
            raise MachineStateError("Error: a safe_z height must be defined before invoking this function")
        return func(self, *args, **kwargs)
    return safe_z_check

class BayesianOptDemoDriver(JubileeMotionController):
    """
    Driver for managing motion commands and other real-world inconveniences.

    Should take high level commands (10 ml red to A1), figure out what that means in XYZ space, and pass to machine. 
    """

    