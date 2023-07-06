# things that users/students are going to be calling. Should take arguments that allow experimentation, manage BO/sampling related stuff
import numpy as np
from . import image_processing as img
import bayesopt.bayesian_optimizer as bayesian_optimizer
import bayesopt.model as model
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process import kernels
import time
import matplotlib.pyplot as plt
import cv2

def sample_point(jubilee, RYB: tuple, volume: float, well: str, file_name: str):
    """
    Sample a specified point. 

    Inputs:
    jubilee - jubilee robot instance
    RYB (tuple) - (R, Y, B) values - either 0-1 or 0-255.
    volume: total sample volume
    well: string well location
    file_name: what to name image file that gets saved


    Returns:
    -------
    RGB - tuple RGB value of resulting solution
    """
    RYB = list(RYB)
    # get the volumes of each color

    RYB = normalize_color(RYB)
    print('RYB after norm in sample func: ', RYB)
    
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
    #sleep so I can stir manually
    #jubilee.move_xy_absolute(x = 20, y = 20)
    #time.sleep(5)
    image = jubilee.well_image(well)

    fp_base = jubilee.config['CAMERA_PI']['image_save_fp']
    filepath = fp_base + '/' + file_name

    # do post-processing 
    RGB = img.process_image(image, filepath)
    
    return RGB, image


def BO_campaign(initial_data, acquisition_function, number_of_iterations, target_color, jubilee):
    """
    This should be a child-safed way to run BO on the platform
    """
    sample_volume = 5 # mL
    n_points = 101

    # define possible sampling grid
    available_points = get_constrained_points(n_points)
    kernel = kernels.Matern(nu = 1/2)
    #kernel = kernels.DotProduct()
    internal_model = model.GaussianProcessModel(kernel, scale = True, alpha = 1e-5)
    acq_kwargs = {'xi':0.25}

    # instantiate a bayesian optimizer object
    bo = bayesian_optimizer.BayesianOptimizer(None, acquisition_function, internal_model, initial_data, valid_points = available_points, acq_kwargs = acq_kwargs)

    # check that we have enough sample wells for the number of iterations we want to run 

    # get first set of points from model
    query_point = bo.campaign_iteration(None, None)[0]


    print('first query pt: ', query_point)
    rgb_values_sampled = []
    ryb_points_sampled = []

    plt.ion()
    fig, ax = plt.subplots(1,2, figsize = (20,8))

    ax[0].set_title('Most Recent Image')
    ax[1].set_title('Color Loss Plot')
    ax[1].set_xlabel('Iteration')
    ax[1].set_ylabel('Loss')
    for i in range(number_of_iterations):
        # query point from BO model
        # get well
        print(f'Starting iteration {i}')
        well = jubilee.next_sample_well()
        # run point in real world
        print(f'Dispensing into well {well}')
        print(f'RYB values tested: {query_point}')
        
        file_name = f'masked_sample_image_batch_{i}.jpg'
        new_color, image = sample_point(jubilee, query_point, sample_volume, well, file_name)

        ryb_points_sampled.append(query_point)
        rgb_values_sampled.append(new_color)
        norm_rgb = normalize_color(new_color)
        score = color_loss_calculation(target_color, normalize_color(norm_rgb))

        print(f'loss score: {score}')
        print(f'RGB values observed: {norm_rgb}')
        query_point = bo.campaign_iteration(query_point, score)[0]

        try:
            plot_results(rgb_values_sampled, target_color, image, fig, ax)
        except Exception as e:
            print(e)
            pass

    return bo, rgb_values_sampled, ryb_points_sampled



def plot_results(rgb_values_sampled, target_color, image, fig, ax):
    # get loss values
    loss_vals = [color_loss_calculation(target_color, normalize_color(rgb)) for rgb in rgb_values_sampled]
    norm_colors = [normalize_color(rgb) for rgb in rgb_values_sampled]
    # plot iteration vs. loss with color observed as marker color

    

    imgbuf = np.frombuffer(image, dtype = np.uint8)
    imgcv = cv2.imdecode(imgbuf, cv2.IMREAD_COLOR)
    imgcv_rgb = imgcv[:,:,[2,1,0]]

    for i, loss in enumerate(loss_vals):
        ax[1].scatter(i, loss_vals[i], marker = 'o', color = norm_colors[i], s = 200)
        ax[0].imshow(imgcv_rgb)

    fig.canvas.draw()

    fig.canvas.flush_events()

    return








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
    distance = [np.abs(np.array(t) - np.array(m)) for t, m in zip(target_color, measured_color)]
    score = np.linalg.norm(distance)

    return 1 - score
