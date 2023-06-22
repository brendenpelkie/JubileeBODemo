"""
script to set up a new piece of labware on the deck. Use this since the deck plate
setup does not work in jupyter
"""

import argparse
from jubileedemo import meatspace_protocols as meat

### parse args

parser = argparse.ArgumentParser()
parser.add_argument('--current_config_fp')
parser.add_argument('--deck_slot')
parser.add_argument('--well_count')
parser.add_argument('--new_config_fp')

args = parser.parse_args()
print(parser)

jub = meat.BayesianOptDemoDriver(deck_config_filepath = args.current_config_fp)

jub.setup_plate(args.deck_slot, args.well_count)

jub.save_deck_config(args.new_config_fp)


