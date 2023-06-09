# this module should handle taking things like "add 5ml of red solution to well A1" and convert that to 'move to XYZ, 'extrude' 5 ml" which will be passed to the jubilee controller

# jubilee generic tool class - no external tool required

# jubilee generic tool class - needs an external tool (ie camera vi rpi)

# for demo: write all of this in one class that does all the functionality. refactor to abstract better once we are doing our own API

#heavilyt copied from sonication_station Joshua Vasquez
import json
import time
from functools import wraps
from .jubilee_controller import JubileeMotionController, MachineStateError
import yaml
import copy
import logging
from jubileedemo.camera import Camera
import pprint
from math import sqrt, acos, asin, cos, sin
import math
import re

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

    CAMERA_FOCAL_LENGTH_OFFSET = 20

    IDLE_Z_HEIGHT = 300

    # TODO: Load this from a config file or read from machine config
    CAMERA_TOOL_INDEX = 0
    DISPENSE_TOOL_INDEX = 1

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
    
    def __init__(self, system_config_filepath = './config.yaml',
               debug = False, simulated = False, deck_config_filepath = "./deck_config.json"):
        
        # load system config
        with open(system_config_filepath, 'rt') as f:
            config = yaml.safe_load(f)

        self.config = config

        self.used_wells = []
        self.sample_plates = config['DECK']['sample_plates']
        #self.green_location = config['DECK']['green_location']
        #self.red_location = config['DECK']['red_location']
        #self.blue_location = config['DECK']['blue_location']
        #self.rinse_location = config['DECK']['rinse_location']
        #self.waste_location = config['DECK']['waste_location']
        self.dispense_config = config['DISPENSE_TOOL']

        super().__init__(address = config['duet']['ip_address'], debug = debug, simulated = simulated)

        self.deck_config_filepath = deck_config_filepath
        self.deck_config = copy.deepcopy(self.__class__.BLANK_DECK_CONFIGURATION)

        self.camera = Camera(config['CAMERA_PI'])

        if deck_config_filepath:
            try:
                self.load_deck_config(deck_config_filepath)
            except FileNotFoundError:
                self.deck_config_filepath = None
                logging.warn(f"Error loading deck configuration from {deck_config_filepath}. File not found")
            except json.decoder.JSONDecodeError as e:
                self.deck_config_filepath = None
                logging.exception(f"Error parsing deck configuration from {deck_config_filepath}. Check for valid JSON formatting")

        self.protocol_methods = self._collect_protocol_methods()

        #self.camera = Camera()

    def _collect_protocol_methods(self):
        """
        Collect all the protocol methods decorated with protocol decorator
        """
        protocol_methods = {}

        def get_dict_attr(obj, attr):
            for obj in [obj] + obj.__class__.mro():
                if attr in obj.__dict__:
                    return obj.__dict__[attr]
            raise AttributeError
        
        for name in dir(self):
            value = get_dict_attr(self, name)
            # spacial case properties
            if isinstance(value, property):
                if hasattr(value.fset, 'is_protocol_method'):
                    protocol_methods[name] = value.fset
                continue
            if isinstance(value, classmethod):
                value = value.__func__
            if hasattr(value, 'is_protocol_method'):
                protocol_methods[name] = value
            
        return protocol_methods
    
    @property
    def safe_z(self):
        """
        return the safe z height
        """
        return self.deck_config["safe_z"]
    
    @safe_z.setter
    def safe_z(self, z: float = None):
        """
        Set the height to be the safe z height. Machine takes current height if none passed.
        Machine will try to retract to this height before making XY moves
        """
        if z is None:
            _, _, z = self.position

        if z < 0:
            raise AssertionError("Error: Safe z value cannot be below 0")
        
        max_z_height = self.axis_limits[2][1]
        # biggest tool offset is a negative number
        max_tool_z_offset = min(self.tool_z_offsets)
        max_safe_z = max_z_height + max_tool_z_offset

        assert z <= max_safe_z, f'Error: Cannot set safe_z to {z}mm. The tallest tool restricts max height to {max_safe_z}mm'

        self.deck_config['safe_z'] = z


    @property
    def idle_z(self):
        return self.deck_config["idle_z"]

    @idle_z.setter
    def idle_z(self, z: float = None):
        if z is None:
            _, _, z = self.position

        assert z > 0, "Error: idle_z value cannot be under 0" 

        max_z_height = self.axis_limits[2][1]
        max_tool_z_offset = min(self.tool_z_offsets)
        max_idle_z = max_z_height + max_tool_z_offset

        assert z <= max_idle_z, f"Error: cannot set idle_z height to {z}mm. The tallest tool restricts max height above bed to {max_idle_z}mm."

        self.deck_config['idle_z'] = z


    def move_xy_absolute(self, x: float = None, y: float = None, wait: bool = False, z_safe = True):
        """
        move in XY, including safeZ restrictions
        """
        if self.safe_z is not None and z_safe:
            super().move_xyz_absolute(z=self.safe_z, wait = False)
        super().move_xyz_absolute(x,y, wait = wait)


    def pickup_tool(self, tool_index: int):
        """
        Pickup a tool by index
        """
        # TODO: This would be cool to tie into the tool object, then have an activate_tool method that starts anything up that is relevant (ie turns on camera)
        
        # make sure new tool won't crash into the bed. Should be safe with all the safez stuff but better safe than sorry

        # TODO: incorporate bedware heights here
        _, _, current_z = self.position
        tool_offsets = self.tool_z_offsets

        #if current_z < tool_offsets[tool_index]:
        if current_z < self.safe_z:
            super().move_xyz_absolute(z = self.safe_z)

        super().pickup_tool(tool_index)


    def park_tool(self):
        if self.active_tool_index < 0: 
            return
        self.move_xy_absolute()
        super().park_tool()


    def home_all(self):
        response = input("WARNING: Is the deck clear of plates? [y/n]")
        if response.lower() in ['y', 'yes']:
            super().home_all()
            self.move_xyz_absolute(z = self.idle_z)
        else:
            print("Aborting homing - please remove all plates from deck first")
    
    
    @requires_safe_z
    def check_plate_registration_points(self, plate_index: int):
        """move to each teach point for the deck plate"""

        REG_POINT = ["Bottom Left", "Bottom Right", "Upper Right"]
        if plate_index < 0 or plate_index != self.__class__.DECK_PLATE_COUNT:
            raise AssertionError(f'Error: Deck plates must fall within the range: [0, {self.__class__.DECK_PLATE_COUNT}]')
        
        if self.active_tool_index != self.__class__.CAMERA_TOOL_INDEX:
            self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)
        
        if self.position[2] < self.safe_z:
            self.move_xyz_absolute(z = self.safe_z)

        try:
            # TODO: Turn on camera feed here
            for index, coords in enumerate(self.deck_config['plates'][str(plate_index)]['corner_well_centroids']):
                if coords is None or coords[0] is None or coords [1] is None:
                    raise AssertionError(f"Error: this reference position for deck plate {plate_index} is not defined")
                self.move_xy_absolute(coords[0], coords[1], wait = True)

                # TODO: make it so user can use jog controls to adjust alignment here
                input(f"Currently positioned at index: {REG_POINT[index]} | {coords}. Press any key to continue.")
        finally:
            # TODO: disable camera feed and park tool
            pass
        self.park_tool()

    
    def load_deck_config(self, file_path: str = None):
        """
        Load deck config from filepath. If no filepath passed, reload from initial config at instantiation
        If no initial config, error out
        """

        if file_path is None and self.deck_config_filepath is None:
            raise AssertionError("Error: No file path specified to load from")
        if file_path is None:
            file_path = self.deck_config_filepath
            print(f"Reloading deck config, any unsaved changes will be overridden.")

        with open(file_path, 'r') as config_file:
            print(f"Loading deck config file from {file_path}")
            self.deck_config = json.loads(config_file.read())
            
            # update saved filepath so we load from/save to here next time
            self.deck_config_filepath = file_path

        self.check_config()


    def save_deck_config(self, file_path: str = None):
        """save the current deck configuration to a file"""

        self.check_config()
        if file_path is None and self.deck_config_filepath is None:
            raise AssertionError('Error: No file path is specified from which to save the deck configuration')
        if file_path is None:
            file_path = self.deck_config_filepath
        
        with open(file_path, 'w+') as config_file:
            json.dump(self.deck_config, config_file, indent = 4)
            print(f"Saving configuration to {file_path}")
            self.deck_config_filepath = file_path


    def show_deck_config(self):
        """render deck config"""

        pprint.pprint(self.deck_config)
        self.check_config()

    def check_config(self):
        """print warnings related to deck config"""
        # trigger a warning if deck config violates safe_z by trying to set it.

        self.safe_z = self.deck_config["safe_z"]
        self.idle_z = self.deck_config["idle_z"]

    @requires_safe_z
    def setup_plate(self, deck_slot: int = None, well_count: int = None, plate_loaded: bool = None):
        """
        configure the plate type and location
        """

        old_plate_config = None
        deck_slot = int(deck_slot)
        well_count = int(well_count)
        deck_index = deck_slot - 1

        try:
            #ask for the deck index if the user didn't input it
            if deck_index is None:
                self.completions = list(map(str, range(self.__class__.DECK_PLATE_COUNT)))
                deck_index = int(input(f"Enter deck slot: ")) - 1


            deck_index_str = str(deck_index)

            #check for existing plate config
            if deck_index_str in self.deck_config['plates']:
                # issue warning that plate exists and bail if canceled by user
                self.completions = ["y", "n"]
                response = input(f"Warning: configuration for deck slot {deck_slot} already exists. Continuing will override this current config. Process? [y/n]")
                if response.lower() not in ["y", "yes"]:
                    print('returning and exiting')
                    return
                old_plate_config = copy.deepcopy(self.deck_config['plates'][deck_index_str])

            #create a new deck configuration from scratch
            self.deck_config['plates'][deck_index_str] = copy.deepcopy(self.__class__.BLANK_DECK_PLATE_CONFIG)

            # ask for well count if the user didn't input
            # TODO: 

            if well_count is None:
                self.completions = list(map(str, self.__class__.WELL_COUNT_TO_ROWS.keys()))
                well_count = int(input(f"Enter number of wells: "))

            self.deck_config['plates'][deck_index_str]["well_count"] = well_count

            #ask if plate is loaded
            if plate_loaded is None:
                plate_loaded = False
                self.completions = ["y", "yes"]
                response = input(f"Is the plate already loaded on deck slot {deck_slot}? ")
                if response.lower() in ['y', 'yes']:
                    plate_loaded = True


            if not plate_loaded:
                self.move_xy_absolute(0,0)
                input(f"please load the plate in deck slot {deck_slot}. "
                           "Press enter when finished")
                
                row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]
                last_row_letter = chr(row_count + 65 -1)

                # part 1: define the plate location with teach points.
                self.enable_live_video()
                #move such that well plates are in focus    
                self.move_xyz_absolute(z = (self.safe_z + self.__class__.CAMERA_FOCAL_LENGTH_OFFSET))

                self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)

                self.move_xyz_absolute(x = self.__class__.DECK_PLATE_NOMINAL_CORNERS[deck_index][0], y = self.__class__.DECK_PLATE_NOMINAL_CORNERS[deck_index][1])

                # collect 3 'teach points' for this plate
                # point 1
                input("Commencing manual zeroing. Press enter when ready or 'CTRL-C' to abort")
                self.keyboard_control(prompt = 'Center the camera over well position A1. ' \
                                      "Press 'q' to set the teach point or 'ctrl-c' to abort")
                self.deck_config['plates'][deck_index_str]['corner_well_centroids'][0] = self.position[0:2]

                # point 2
                input("Commencing manual zeroing. Press enter when ready or 'CTRL-C' to abort")
                self.keyboard_control(prompt = f'Center the camera over well position A{col_count}. ' \
                                      "Press 'q' to set the teach point or 'ctrl-c' to abort")
                self.deck_config['plates'][deck_index_str]['corner_well_centroids'][1] = self.position[0:2]

                # point 3
                input("Commencing manual zeroing. Press enter when ready or 'CTRL-C' to abort")
                self.keyboard_control(prompt = f'Center the camera over well position {last_row_letter}{col_count}. ' \
                                      "Press 'q' to set the teach point or 'ctrl-c' to abort")
                self.deck_config['plates'][deck_index_str]['corner_well_centroids'][2] = self.position[0:2]

                self.disable_live_video()

                # part 2: define the plate height with the tool
                self.move_xy_absolute() # safe z

                self.pickup_tool(self.__class__.DISPENSE_TOOL_INDEX)
                x, y = self._get_well_position(deck_index, 0, 0)
                self.move_xy_absolute(x, y)
                input("In the next step set the reference point from where the dispense depth is measured. This is set from the topmost part of the plate well or vessel\r\n" 
                           "Press enter when ready")
                self.keyboard_control(prompt = "move the syringe tip to a heigh where it just clears the plate or vessel \r\n" 
                                      "Press 'q to set the height or 'ctrl-c' to abort")
                _, _, plate_height = self.position

                self.deck_config['plates'][deck_index_str]['plate_height'] = plate_height

        except KeyboardInterrupt:
            print('Aborting. Well locations not saved')
            
            if old_plate_config:
                self.deck_config['plates'][deck_index_str] = old_plate_config
            
        finally:
                self.disable_live_video()

        self.park_tool()

    def volume_to_distance(volume: float):
        """
        Convert volume to syringe extrusion distance"""

        distance = volume*area

    def pickup_dispense_tool(self):
        #TODO: Make this a general function for all tools
        """
        Internal check to verify dispense tool is picked up and 
        """
        if self.active_tool_index != self.__class__.DISPENSE_TOOL_INDEX:
            if self.active_tool_index == -1:
                self.pickup_tool(self.__class__.DISPENSE_TOOL_INDEX)
            else:
                self.park_tool()
                self.pickup_tool(self.__class__.DISPENSE_TOOL_INDEX)

        return True
    
    def pickup_camera_tool(self):
        """
        ick ick ick fix so this is one func for all that does this
        """
        print('current active tool: ', self.active_tool_index)
        if self.active_tool_index != self.__class__.CAMERA_TOOL_INDEX:
            if self.active_tool_index == -1:
                self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)
            else:
                self.park_tool()
                self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)

        return True
    
    def _pippette_location(self, well, pippette_index):
        plate, row, col = self._location_to_index(well)
        #print("location indices: ", plate, row, col)
        coordinates = self._get_well_position(plate, row, col)
        #print('dispense coordintes: ', coordinates)


        # apply pippette offset
        assert int(pippette_index) in [0,1,2], 'ERROR: Please choose a valid pippette index out of 0, 1, 2'
  
        pippette_offset = eval(self.dispense_config[f'pippette_{pippette_index}_offsets'])
        dispense_tool_coordinate = [float(coord) + float(off) for coord, off in zip(coordinates, pippette_offset)]

        return dispense_tool_coordinate


    @requires_safe_z
    def dispense(self, well: str, volume: float, pippette_index: int, safe_z = True):

        """
        Dispense a volume of liquid to a well
        well (str, ex 1.A1)
        volume: volume in mL to dispense
        pippette_index: which pippette to use 
        safe_z - disable z safe height moves if doing a series of dispense in one well or in a row
        """
        # if no volume dispensed, don't do anything
        if volume == 0:
            return
        # assert dispense tool is picked up
        _ = self.pickup_dispense_tool()

        plate, row, col = self._location_to_index(well)
        dispense_tool_coordinate = self._pippette_location(well, pippette_index)
        # move to well location
        self.move_xy_absolute(x = dispense_tool_coordinate[0], y = dispense_tool_coordinate[1], z_safe= safe_z)

        # move to dispense height
        dispense_height = self.deck_config['plates'][str(plate)]['plate_height']
        self.move_xyz_absolute(z = dispense_height)

        # dispense
        self._peristaltic_pump(pippette_index, volume)
        time.sleep(0.5)
        # move back to safe z height
        self.move_xyz_absolute(z = dispense_height + 3)
        

        return
    @requires_safe_z
    def well_image(self, well):
        """
        Get an image from a well
        """
        _ = self.pickup_camera_tool()

        plate, row, col = self._location_to_index(well)
        coordinates = self._get_well_position(plate, row, col)
        # move to well location
        self.move_xyz_absolute(z = (self.safe_z + self.__class__.CAMERA_FOCAL_LENGTH_OFFSET))
        self.move_xy_absolute(x = coordinates[0], y = coordinates[1])
        time.sleep(3)
        image = self.camera.capture_image()

        return image




    def _peristaltic_pump(self, pippette_index: int, volume: float):
        """
        actually activate pump
        """
        volumes = [0,0,0]
        volumes[pippette_index] = volume
        stringvol = ':'.join([str(v) for v in volumes]) # negative b/c gcode pump reverse is suspect for now

        self.gcode(f'G1 E{stringvol}')

        return
    
    def prime_lines(self, well, volume = 35):
        """
        Prime all the lines with 35 ml of milk
        """
        pippette_index = 0

        # assert dispense tool is picked up
        _ = self.pickup_dispense_tool()

        plate, row, col = self._location_to_index(well)
        dispense_tool_coordinate = self._pippette_location(well, pippette_index)
        # move to well location
        self.move_xy_absolute(x = dispense_tool_coordinate[0], y = dispense_tool_coordinate[1])

        # move to dispense height
        dispense_height = self.deck_config['plates'][str(plate)]['plate_height']
        self.move_xyz_absolute(z = dispense_height)
        
        volumes = [str(volume)]*3
        stringvol = ':'.join(volumes)
    

        self.gcode(f'G1 E{stringvol}')

        self.move_xyz_absolute(z = dispense_height + 5)

        return
    

    def prepare_RGB_sample(RGB:tuple, deck_location: str):
        """
        prepare a sample of RGB mixes
        
        RGB (tuple) - tuple of volumes of red, green, blue solutions to use
        deck location (str) - deck location in 'plate#.well' format ex '6.A1'
        """


    
    def execute_protocol_from_file(self, protocol_file_path):
        """Open the protocol file and run the protocol."""
        with open(protocol_file_path, 'r') as protocol_file:
            protocol = json.loads(protocol_file.read())
            self.execute_protocol(protocol)


    def execute_protocol(self, protocol):
        """execute a list of commands"""
        for cmd in protocol:
            if cmd['operation'] not in self.protocol_methods:
                raise AssertionError(f"Error: Method {cmd['operation']} is not a method available to protocols")
            fn = self.protocol_methods[cmd['operation']]
            kwargs = cmd['specs']
            kwargs['self'] = self
            fn(**kwargs)


    def enable_live_video(self):
        self.camera.video_feed()
    
    def disable_live_video(self):
        """
        we're just gonna get a bunch of browser tabs and live with it"""
        pass
    
    def next_sample_well(self):
        """
        Return the well location of the next available sample well
        """
        #TODO: Make increment right

        # get last used well
        if len(self.used_wells) == 0:
            plate = self.sample_plates[0]
            plate_index = plate - 1
            new_well = str(plate) + '.A1'
            self.used_wells.append(new_well)
            return new_well
            
        last_well = self.used_wells[-1]
        last_plate, last_row, last_col = self.process_string_location(last_well)
        last_plate_index = int(last_plate) - 1

        plate_well_count = self.deck_config['plates'][str(last_plate_index)]['well_count']
        
        row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[plate_well_count]
        last_row_letter = chr(row_count + 65 -1)

        if int(col_count) == int(last_col):
            if last_row_letter == last_row:
                if int(self.sample_plates[-1]) == int(last_plate):
                    # we've run out of plates
                    raise RuntimeError("Error: All available sample wells have been used")
                    # TODO: allow user to refresh all plates and continue experiment
                else:
                    old_plate_index = [i for i, plate in enumerate(self.sample_plates) if int(plate) == int(last_plate)][0]
                    new_plate = self.sample_plates[old_plate_index + 1]
                    new_col = 1
                    new_row = 'A'
            else:
                new_col = 1
                new_row = chr(ord(last_row.upper())+1)
                new_plate = last_plate
        else:
            new_col = int(last_col) + 1
            new_row = last_row
            new_plate = last_plate

        new_well = str(new_plate) + '.' + str(new_row) + str(new_col)
        self.used_wells.append(new_well)

        return new_well
    
    def clear_well_usage(self):
        """
        Reset the sample wells to clean in Jubilee's tracker
        """
        self.used_wells = []

    
    def process_string_location(self, loc:str):
        """
        Convert '1.A1' string to plate, row, col index"""

        plate, well = loc.split('.')
        try:
            plate_index = int(plate)
        except ValueError:
            raise AssertionError(f'Error: plate indices must be integers, not {plate}')
    
        #assert len(well) == 2, 'Error: Well location must be an alphanumeric code like "A1"'

        row_index, col_index = re.match(r"([a-z]+)([0-9]+)", well, re.I).groups()


        return plate, row_index, col_index
    
    def _location_to_index(self, loc:str):
        """
        Convert '1.A1' location to integer indices
        """

        plate, row, column = self.process_string_location(loc)

        plate_index = int(plate) - 1
        row_index = ord(row) - 65
        column_index = int(column) - 1

        return plate_index, row_index, column_index
    
    def _norm_angle(self, angle):
        """
        Adjust plate angles so they are around 0 rads so that averaging works
        """
        angle = angle % math.pi
        if angle > math.pi/2:
            angle = angle - math.pi

        return angle


    
    def _get_well_position(self, deck_index: int, row_index:int, col_index:int):
        """
        get machine coords for string well location
        """

        deck_index_str = str(deck_index)

        # look up well spacing from built-in dict
        well_count = self.deck_config['plates'][deck_index_str]['well_count']
        row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]

        if row_index > (row_count - 1) or col_index > (col_count -1):
            raise LookupError(f"Requested well index ({row_index}, {col_index}) is out of bounds for plate with {row_count} rows and {col_count} columns")
        
        a = self.deck_config['plates'][deck_index_str]["corner_well_centroids"][0]
        b = self.deck_config['plates'][deck_index_str]["corner_well_centroids"][1]
        c = self.deck_config['plates'][deck_index_str]["corner_well_centroids"][2]

        # I think this lets us deal with plates that are not perfectly square to the frame
        plate_width = sqrt((b[0] - a[0])**2 + (b[1] - a[1])**2)
        plate_height = sqrt((c[0] - b[0])**2 + (c[1] - b[1])**2)

        #print('a: ', a)
        #print('b: ', b)
        #print('c: ', c)

        #print('height: ', plate_height)
        #print('width: ', plate_width)

        x_spacing = plate_width/(col_count - 1)
        y_spacing = plate_height/(row_count - 1)

        # average the two angle measurements

        theta1 = acos((c[1] - b[1])/plate_height)
        theta2 = acos((b[0] - a[0])/plate_width)

        theta1 = self._norm_angle(theta1)
        theta2 = self._norm_angle(theta2)

        theta = (theta1 + theta2)/2


        #print('theta :', theta)
        # translate/rotate nominal spot to actual spot
            
        x_nominal = col_index * x_spacing
        y_nominal = row_index * y_spacing

        #print('x nominal: ', x_nominal)
        #print('y nominal: ', y_nominal)

        #print('x adjust for well: ', x_nominal * cos(theta) - y_nominal * sin(theta))
        #print('y adjust for well: ', x_nominal * sin(theta) + y_nominal * cos(theta))

        #print('location offset: ', a)

        x_transformed = -(x_nominal * cos(theta) - y_nominal * sin(theta)) + a[0]
        y_transformed = x_nominal * sin(theta) + y_nominal * cos(theta) + a[1]

        return x_transformed, y_transformed
    

    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.disable_live_video()
        if all(self.axes_homed):
            self.park_tool()
            self.move_xyz_absolute(z = self.idle_z)

        super().__exit__(args)




        