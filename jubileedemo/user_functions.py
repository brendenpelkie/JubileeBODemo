# things that users/students are going to be calling. Should take arguments that allow experimentation, manage BO/sampling related stuff

def sample_point(RGB: tuple, volume: float):
    """
    Sample a specified point. 

    Inputs:
    RGB (tuple) - (R, G, B) values - either 0-1 or 0-255.
    volume: total sample volume
    """


def BO_campaign(initial_data, acquisistion_function, number_of_iterations, jubilee_instance):
    """
    This should be a child-safed way to run BO on the platform
    """

    # define possible sampling grid
    # we know we are working with a 3-variable constrained design space here so can just hard-code that

    # instantiate a bayesian optimizer object

    # check that we have enough sample wells for the number of iterations we want to run 

    # for each iteration:
        # query point from BO model

        # run point in real world

        # call the deck manager to get the next well location

        # call the prep_sample function to build the sample

        # call the camera motion control function to go take a picture of the sample

        # call the image processing module to get the RGB values

        # check convergence criteria

        # update BO model, data