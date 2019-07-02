# coding=utf-8
from collections import OrderedDict
from itertools import izip, cycle

import numpy as np
from scipy.signal import decimate, convolve, detrend, hilbert
from scipy.stats import zscore
from pylab import demean

from tvb_utils.log_error_utils import raise_value_error, initialize_logger
from tvb_utils.data_structures_utils import isequal_string, ensure_list, is_integer
from tvb_utils.computations_utils import select_greater_values_array_inds,\
    select_by_hierarchical_group_metric_clustering
from tvb_utils.analyzers_utils import abs_envelope, spectrogram_envelope, filter_data
from tvb_timeseries.timeseries import TimeseriesDimensions


def decimate_signals(signals, time, decim_ratio):
    if decim_ratio > 1:
        signals = decimate(signals, decim_ratio, axis=0, zero_phase=True, ftype="fir")
        time = decimate(time, decim_ratio, zero_phase=True, ftype="fir")
        dt = np.mean(np.diff(time))
        (n_times, n_signals) = signals.shape
        return signals, time, dt, n_times


def cut_signals_tails(signals, time, cut_tails):
    signals = signals[cut_tails[0]:-cut_tails[-1]]
    time = time[cut_tails[0]:-cut_tails[-1]]
    (n_times, n_signals) = signals.shape
    return signals, time, n_times


NORMALIZATION_METHODS = ["zscore", "mean","min", "max", "baseline", "baseline-amplitude", "baseline-std", "minmax"]


def normalize_signals(signals, normalization=None, axis=None, percent=None):

    # Following pylab demean:

    def matrix_subtract_along_axis(x, y, axis=0):
        "Return x minus y, where y corresponds to some statistic of x along the specified axis"
        if axis == 0 or axis is None or x.ndim <= 1:
            return x - y
        ind = [slice(None)] * x.ndim
        ind[axis] = np.newaxis
        return x - y[ind]

    def matrix_divide_along_axis(x, y, axis=0):
        "Return x divided by y, where y corresponds to some statistic of x along the specified axis"
        if axis == 0 or axis is None or x.ndim <= 1:
            return x / y
        ind = [slice(None)] * x.ndim
        ind[axis] = np.newaxis
        return x / y[ind]


    for norm, ax, prcnd in izip(ensure_list(normalization), cycle(ensure_list(axis)), cycle(ensure_list(percent))):
        if isinstance(norm, basestring):
            if isequal_string(norm, "zscore"):
                signals = zscore(signals, axis=ax)  # / 3.0
            elif isequal_string(norm, "baseline-std"):
                signals = normalize_signals(["baseline", "std"], axis=axis)
            elif norm.find("baseline") == 0 and norm.find("amplitude") >= 0:
                signals = normalize_signals(signals, ["baseline", norm.split("-")[1]], axis=axis, percent=percent)
            elif isequal_string(norm, "minmax"):
                signals = normalize_signals(signals, ["min", "max"], axis=axis)
            elif isequal_string(norm, "mean"):
                signals = demean(signals, axis=ax)
            elif isequal_string(norm, "baseline"):
                if prcnd is None:
                    prcnd = 1
                signals = matrix_subtract_along_axis(signals, np.percentile(signals, prcnd, axis=ax), axis=ax)
            elif isequal_string(norm, "min"):
                signals = matrix_subtract_along_axis(signals, np.min(signals, axis=ax), axis=ax)
            elif isequal_string(norm, "max"):
                signals = matrix_divide_along_axis(signals, np.max(signals, axis=ax), axis=ax)
            elif isequal_string(norm, "std"):
                signals = matrix_divide_along_axis(signals, signals.std(axis=ax), axis=ax)
            elif norm.find("amplitude") >= 0:
                if prcnd is None:
                    prcnd = [1, 99]
                amplitude = np.percentile(signals, prcnd[1], axis=ax) - np.percentile(signals, prcnd[0], axis=ax)
                this_ax = ax
                if isequal_string(norm.split("amplitude")[0], "max"):
                    amplitude = amplitude.max()
                    this_ax=None
                elif isequal_string(norm.split("amplitude")[0], "mean"):
                    amplitude = amplitude.mean()
                    this_ax = None
                signals = matrix_divide_along_axis(signals, amplitude, axis=this_ax)
            else:
                raise_value_error("Ignoring signals' normalization " + normalization +
                                  ",\nwhich is not one of the currently available " + str(NORMALIZATION_METHODS) + "!")
    return signals


class TimeseriesService(object):

    logger = initialize_logger(__name__)

    def __init__(self, logger=initialize_logger(__name__)):

        self.logger = logger

    def decimate(self, timeseries, decim_ratio):
        if decim_ratio > 1:
            return timeseries.__class__(timeseries.data[0:timeseries.time_length:decim_ratio],
                                        timeseries.dimension_labels, timeseries.time_start,
                                        decim_ratio*timeseries.time_step, timeseries.time_unit)
        else:
            return timeseries

    def decimate_by_filtering(self, timeseries, decim_ratio):
        if decim_ratio > 1:
            decim_data, decim_time, decim_dt, decim_n_times = decimate_signals(timeseries.squeezed,
                                                                               timeseries.time, decim_ratio)
            return timeseries.__class__(decim_data, timeseries.dimension_labels,
                                        decim_time[0], decim_dt, timeseries.time_unit)
        else:
            return timeseries

    def convolve(self, timeseries, win_len=None, kernel=None):
        n_kernel_points = np.int(np.round(win_len))
        if kernel is None:
            kernel = np.ones((n_kernel_points, 1, 1, 1)) / n_kernel_points
        else:
            kernel = kernel * np.ones((n_kernel_points, 1, 1, 1))
        return timeseries.__class__(convolve(timeseries.data, kernel, mode='same'), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def hilbert_envelope(self, timeseries):
        return timeseries.__class__(np.abs(hilbert(timeseries.data, axis=0)), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def spectrogram_envelope(self, timeseries, lpf=None, hpf=None, nperseg=None):
        data, time = spectrogram_envelope(timeseries.squeezed, timeseries.sampling_frequency, lpf, hpf, nperseg)
        if len(timeseries.time_unit) > 0 and timeseries.time_unit[0] == "m":
            time *= 1000
        return timeseries.__class__(data,
                                    timeseries.dimension_labels, timeseries.time_start+time[0],
                                    np.diff(time).mean(), timeseries.time_unit)

    def abs_envelope(self, timeseries):
        return timeseries.__class__(abs_envelope(timeseries.data), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def detrend(self, timeseries, type='linear'):
        return timeseries.__class__(detrend(timeseries.data, axis=0, type=type), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def normalize(self, timeseries, normalization=None, axis=None, percent=None):
        return timeseries.__class__(normalize_signals(timeseries.data, normalization, axis, percent),
                                    timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def filter(self, timeseries, lowcut=None, highcut=None, mode='bandpass', order=3):
        return timeseries.__class__(filter_data(timeseries.data, timeseries.sampling_frequency,
                                                lowcut, highcut, mode, order),
                                    timeseries.dimension_labels, timeseries.time_start, timeseries.time_step,
                                    timeseries.time_unit)

    def log(self, timeseries):
        return timeseries.__class__(np.log(timeseries.data), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def exp(self, timeseries):
        return timeseries.__class__(np.exp(timeseries.data), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def abs(self, timeseries):
        return timeseries.__class__(np.abs(timeseries.data), timeseries.dimension_labels,
                                    timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def power(self, timeseries):
        return np.sum(self.square(self.normalize(timeseries, "mean", axis=0)).squeezed, axis=0)

    def square(self, timeseries):
        return timeseries.__class__(timeseries.data ** 2, timeseries.dimension_labels,
                                   timeseries.time_start, timeseries.time_step, timeseries.time_unit)

    def correlation(self, timeseries):
        return np.corrcoef(timeseries.squeezed.T)

    def concatenate_in_time(self, timeseries_list, labels=None):
        timeseries_list = ensure_list(timeseries_list)
        out_timeseries = timeseries_list[0]
        if labels is None:
            labels = out_timeseries.space_labels
        else:
            out_timeseries = out_timeseries.get_subspace_by_labels(labels)
        for id, timeseries in enumerate(timeseries_list[1:]):
            if np.float32(out_timeseries.time_step) == np.float32(timeseries.time_step):
                out_timeseries.data = np.concatenate([out_timeseries.data,
                                                      timeseries.get_subspace_by_labels(labels).data], axis=0)
            else:
                raise_value_error("Timeseries concatenation in time failed!\n"
                                  "Timeseries %d have a different time step (%s) than the ones before(%s)!" \
                                  % (id, str(np.float32(timeseries.time_step)),
                                     str(np.float32(out_timeseries.time_step))))
        return out_timeseries

    def select_by_metric(self, timeseries, metric, metric_th=None, metric_percentile=None, nvals=None):
        selection = np.unique(select_greater_values_array_inds(metric, metric_th, metric_percentile, nvals))
        return timeseries.get_subspace_by_index(selection), selection

    def select_by_power(self, timeseries, power=np.array([]), power_th=None):
        if len(power) != timeseries.number_of_labels:
            power = self.power(timeseries)
        return self.select_by_metric(timeseries, power, power_th)

    def select_by_hierarchical_group_metric_clustering(self, timeseries, distance, disconnectivity=np.array([]),
                                                       metric=None, n_groups=10, members_per_group=1):
        selection = np.unique(select_by_hierarchical_group_metric_clustering(distance, disconnectivity, metric,
                                                                             n_groups, members_per_group))
        return timeseries.get_subspace_by_index(selection), selection

    def select_by_correlation_power(self, timeseries, correlation=np.array([]), disconnectivity=np.array([]),
                                    power=np.array([]), n_groups=10, members_per_group=1):
        if correlation.shape[0] != timeseries.number_of_labels:
            correlation = self.correlation(timeseries)
        if len(power) != timeseries.number_of_labels:
            power = self.power(timeseries)
        return self.select_by_hierarchical_group_metric_clustering(timeseries, 1-correlation,
                                                                   disconnectivity, power, n_groups, members_per_group)

    def select_by_gain_matrix_power(self, timeseries, gain_matrix=np.array([]),
                                    disconnectivity=np.array([]), power=np.array([]),
                                    n_groups=10, members_per_group=1):
        if len(power) != timeseries.number_of_labels:
            power = self.power(timeseries)
        return self.select_by_hierarchical_group_metric_clustering(timeseries, 1-np.corrcoef(gain_matrix),
                                                                   disconnectivity, power, n_groups, members_per_group)

    def select_by_rois_proximity(self, timeseries, proximity, proximity_th=None, percentile=None, n_signals=None):
        initial_selection = range(timeseries.number_of_labels)
        selection = []
        for prox in proximity:
            selection += (
                np.array(initial_selection)[select_greater_values_array_inds(prox, proximity_th,
                                                                             percentile, n_signals)]).tolist()
        selection = np.unique(selection)
        return timeseries.get_subspace_by_index(selection), selection

    def select_by_rois(self, timeseries, rois, all_labels):
        for ir, roi in rois:
            if not(isinstance(roi, basestring)):
                rois[ir] = all_labels[roi]
        return timeseries.get_subspace_by_labels(rois), rois

    def compute_seeg(self, source_timeseries, sensors, sum_mode="lin"):
        if np.all(sum_mode == "exp"):
            seeg_fun = lambda source, gain_matrix: compute_seeg_exp(source.squeezed, gain_matrix)
        else:
            seeg_fun = lambda source, gain_matrix: compute_seeg_lin(source.squeezed, gain_matrix)
        if isinstance(sensors, dict):
            seeg = OrderedDict()
            for sensor_name, sensor in sensors.items():
                seeg[sensor_name] = source_timeseries.__class__(seeg_fun(source_timeseries, sensor.gain_matrix),
                                                                {TimeseriesDimensions.SPACE.value: sensor.labels,
                                                                 TimeseriesDimensions.VARIABLES.value: [sensor.name]},
                                                                source_timeseries.time_start,
                                                                source_timeseries.time_step,
                                                                source_timeseries.time_unit)
            return seeg
        else:
            return source_timeseries.__class__(seeg_fun(source_timeseries, sensors.gain_matrix),
                                                {TimeseriesDimensions.SPACE.value: sensors.labels,
                                                 TimeseriesDimensions.VARIABLES.value: [sensors.name]},
                                                source_timeseries.time_start, source_timeseries.time_step,
                                                source_timeseries.time_unit)


def compute_seeg_lin(source_timeseries, gain_matrix):
    return source_timeseries.dot(gain_matrix.T)


def compute_seeg_exp(source_timeseries, gain_matrix):
    return np.log(np.exp(source_timeseries).dot(gain_matrix.T))









