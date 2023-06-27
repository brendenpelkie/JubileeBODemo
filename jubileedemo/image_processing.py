import cv2
import numpy as np
import time


def process_image(image_bin):
    """
    externally callable function to run processing pipeline
    
    takes an image as a bstring
    """
    image_arr = np.frombuffer(image_bin, np.uint8)
    image = cv2.imdecode(image_arr, cv2.IMREAD_COLOR)
    radius = 50
    masked_image = _mask_image(image, radius)
    t = time.time()
    cv2.imwrite(f'./sampleimage_full_{t}.jpg', image)
    cv2.imwrite(f'./sampleimage_masked_{t}.jpg', masked_image)
    values = _get_rgb_avg(masked_image)
    return values



def _mask_image(image, radius):

    mask = np.zeros(image.shape[:2], dtype = "uint8")
    cv2.circle(mask, (300, 300), radius, 255, -1)
    masked = cv2.bitwise_and(image, image, mask=mask)

    return masked



def _get_rgb_avg(image):
    bgr = []
    for dim in [0,1,2]:
        flatdim = image[:,:,dim].flatten()
        indices = flatdim.nonzero()[0]
        value = flatdim.flatten()[indices].mean()
        bgr.append(value)

    #opencv uses bgr so convert to rgb for loss
    print('swapping')
    rgb = [bgr[i] for i in [2,1,0]]
    return rgb
