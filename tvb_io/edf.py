# coding=utf-8

from mne.io import read_raw_edf

import numpy as np

from tvb_utils.log_error_utils import initialize_logger
from tvb_utils.data_structures_utils import ensure_string
from tvb_timeseries.model.timeseries import Timeseries, TimeseriesDimensions

def read_edf(path, sensors, rois_selection=None, label_strip_fun=None, time_units="ms", exclude_channels=[]):
    logger = initialize_logger(__name__)

    logger.info("Reading empirical dataset from mne file...")
    raw_data = read_raw_edf(path, preload=True, exclude=exclude_channels)

    if not callable(label_strip_fun):
        label_strip_fun = lambda label: label

    channel_names = [label_strip_fun(s) for s in raw_data.ch_names]

    rois = []
    rois_inds = []
    rois_lbls = []
    if len(rois_selection) == 0:
        rois_selection = sensors.labels

    logger.info("Selecting target signals from dataset...")
    for sensor_ind, sensor_label in enumerate(sensors.labels):
        if sensor_label in rois_selection and sensor_label in channel_names:
            rois.append(channel_names.index(sensor_label))
            rois_inds.append(sensor_ind)
            rois_lbls.append(sensor_label)

    data, times = raw_data[:, :]
    data = data[rois].T
    # Assuming that edf file time units is "sec"
    if ensure_string(time_units).find("ms") == 0:
        times = 1000 * times
    # sort_inds = np.argsort(rois_lbls)
    rois = np.array(rois) # [sort_inds]
    rois_inds = np.array(rois_inds) # [sort_inds]
    rois_lbls = np.array(rois_lbls) # [sort_inds]
    # data = data[:, sort_inds]

    return data, times, rois, rois_inds, rois_lbls


def read_edf_to_Timeseries(path, sensors, rois_selection=None, label_strip_fun=None, time_units="ms"):
    data, times, rois, rois_inds, rois_lbls = \
        read_edf(path, sensors, rois_selection, label_strip_fun, time_units)

    return Timeseries(data, {TimeseriesDimensions.SPACE.value: rois_lbls},
                      times[0], np.mean(np.diff(times)), time_units)