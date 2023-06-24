# things that users/students are going to be calling. Should take arguments that allow experimentation, manage BO/sampling related stuff
import numpy as np
from . import image_processing as img
import bayesopt.bayesian_optimizer as bayesian_optimizers

def sample_point(jubilee, RYB: tuple, volume: float, well):
    """
    Sample a specified point. 

    Inputs:
    RYB (tuple) - (R, Y, B) values - either 0-1 or 0-255.
    volume: total sample volume

    Returns:
    -------
    RGB - tuple RGB value of resulting solution
    """
    RYB = list(RYB)
    # get the volumes of each color

    RYB = normalize_color(RYB)
    
    volumes = [vf*volume for vf in RYB]    
    

    # convert color to pippette index
    # hard-coded pippette indices for now
    red = 0
    yellow = 1
    blue = 2

    # get the well that we want to mix in
    # assume this is passed to function
    print('Dispensing volumes: ', volumes)

    # dispense volumes into well
    jubilee.dispense(well, volumes[0], red)
    jubilee.dispense(well, volumes[1], yellow, safe_z = False)
    jubilee.dispense(well, volumes[2], blue, safe_z = False)
    # measure well with camera
    image = jubilee.well_image(well)

    # do post-processing 
    RGB = img.process_image(image)
    
    return RGB


def BO_campaign(initial_data, acquisition_function, number_of_iterations, target_color, jubilee):
    """
    This should be a child-safed way to run BO on the platform
    """
    sample_volume = 5 # mL
    n_points = 101

    # define possible sampling grid
    available_points = get_constrained_points(n_points)
    # we know we are working with a 3-variable constrained design space here so can just hard-code that
    # instantiate a bayesian optimizer object
    bo = bayesian_optimzer.BayesianOptimizer(None, acquisition_function, None, initial_data)

    # check that we have enough sample wells for the number of iterations we want to run 

    # get first set of points from model
    query_point = bo.campaign_iteration(None, None)

    for i in range(number_of_iterations):
        # query point from BO model
        # get well
        print(f'Starting iteration {i}')
        well = jubilee.next_sample_well()
        # run point in real world
        print(f'Dispensing into well {well}')
        print('RYB values tested: {query_point}')
        new_color = sample_point(jubilee, query_point, sample_volume, well)

        score = color_loss_calculation(target_color, new_color)

        print('RGB values observed: {RGB}')
        query_point = bo.campaign_iteration(query_point, new_color)




def get_constrained_points(n_points):
    """
    Get the available points in 3-dimensional sample space with volumetric mixing constraint
    """


    R = np.linspace(0, 1, n_points)
    Y = np.linspace(0, 1, n_points)
    B = np.linspace(0,1, n_points)

    # do a brute force constrained sampling to get points in the design space
    test_arr = np.array(np.meshgrid(R, Y, B)).T.reshape(-1,3)
    indices = np.where(test_arr.sum(axis = 1) != 1)[0]
    testable_points = np.delete(test_arr, indices, axis = 0)

    return testable_points

def initial_random_sample(testable_points, n_sample = 12):
    """
    Sample n_sample points from testable_points to get initial data
    """
    rng = np.random.default_rng(seed = 4)
    selected_inds = rng.integers(0, len(testable_points), n_sample)
    selected_points = testable_points[selected_inds, :]
   
    return selected_points

def normalize_color(RYB):
    """
    normalize 0-255 or 0-1 to 0-1
    """
    RYB = list(RYB)
    if np.any([v > 1 for v in RYB]):
        RYB = [i/255 for i in RYB]
    return RYB


def color_loss_calculation(target_color, measured_color):
    """
    Get the score for a point
    """
    distance = [abs(t,m) for t,m in zip(target_color, measured_color)]
    score = np.linalg.norm(distance)

    return 1 - score
