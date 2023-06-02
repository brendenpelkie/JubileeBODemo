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

    WELL_COUNT_TO_ROWS = {96: (8, 12), 
                          48: (6, 8),
                          6: (2,3),
                          24: (4, 6), 
                          12: (3, 4)}
    DECK_PLATE_COUNT = 6

    DECK_PLATE_NOMINAL_CORNERS = [(287.75, 289.75),
                                  (148.25, 289.5),
                                  (287.625, 192.25),
                                  (148.125, 192),
                                  (287.75, 94.688),
                                  (148.312, 94.5)]
    
    NOMINAL_WELL_CORNERS = [(),(),(),(),(),()]

    CAMERA_FOCAL_LENGTH_ODDSET = 20

    IDLE_Z_HEIGHT = 300

    # TODO: Load this from a config file or read from machine config
    CAMERA_TOOL_INDEX = 1
    SYRINGE_TOOL_INDEX = 2

    BLANK_DECK_CONFIGURATION = \
        {"plates": {},
         "safe_z": None,
         "idle_z": IDLE_Z_HEIGHT,
         "cleaning_config": {}
         }
    
    BLANK_DECK_PLATE_CONFIG = \
        {"id":"",
         "corner_well_centroids": [(None, None), (None, None), (None, None)],
         "well_count":None,
         "liquid_level":{}
         }
    
    BLANK_CLEANING_CONFIG = \
        {"plates":[],
         "protocol":[]
         }
    
    SPLASH = \
        """
        _       _     _ _             _____                       
        | |     | |   (_) |           |  __ \                      
        | |_   _| |__  _| | ___  ___  | |  | | ___ _ __ ___   ___  
    _   | | | | | '_ \| | |/ _ \/ _ \ | |  | |/ _ \ '_ ` _ \ / _ \ 
    | |__| | |_| | |_) | | |  __/  __/ | |__| |  __/ | | | | | (_) |
    \____/ \__,_|_.__/|_|_|\___|\___| |_____/ \___|_| |_| |_|\___/
        """
    
    def __init(self, system_config_filepath = './confg.yaml',
               debug = False, simulated = False, deck_config_filepath = "./deck_config.json")
        
        super().__init__(address = address)
    