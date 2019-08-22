# coding=utf-8
from six import string_types
from enum import Enum
from copy import deepcopy

import numpy

from tvb.basic.profile import TvbProfile

TvbProfile.set_profile(TvbProfile.LIBRARY_PROFILE)

from tvb_utils.log_error_utils import initialize_logger, raise_value_error, warning
from tvb_utils.data_structures_utils import \
    ensure_list, labels_to_inds, isequal_string, monopolar_to_bipolar, is_integer, is_numeric
from tvb_head.model.sensors import Sensors
from tvb_head.model.surface import Surface

from tvb.datatypes.time_series import \
    TimeSeries, TimeSeriesRegion, TimeSeriesEEG, TimeSeriesMEG, TimeSeriesSEEG, TimeSeriesSurface, TimeSeriesVolume
from tvb.datatypes.sensors import Sensors as TVBSensors, SensorsEEG as TVBSensorsEEG, SensorsMEG as TVBSensorsMEG, \
    SensorsInternal as TVBSensorsInternal
from tvb.datatypes.surfaces import Surface as TVBSurface


class TimeseriesDimensions(Enum):
    TIME = "Time"
    VARIABLES = "State Variables"
    SPACE = "Space"
    SAMPLES = "Samples"


LABELS_ORDERING = [TimeseriesDimensions.TIME.value,
                   TimeseriesDimensions.VARIABLES.value,
                   TimeseriesDimensions.SPACE.value,
                   TimeseriesDimensions.SAMPLES.value]


class PossibleVariables(Enum):
    LFP = "lfp"
    SOURCE = "source"
    EEG = "eeg"
    MEEG = "meeg"
    SEEG = "seeg"


def prepare_4D(data, logger=initialize_logger(__name__)):
    if data.ndim < 2:
        logger.error("The data array is expected to be at least 2D!")
        raise ValueError
    if data.ndim < 4:
        if data.ndim == 2:
            data = numpy.expand_dims(data, 2)
        data = numpy.expand_dims(data, 3)
    return data


def labels_to_indices(labels, target_labels, variables_name, logger):
    indices = []
    target_labels = numpy.unique(ensure_list(target_labels))
    if len(target_labels) > 0:
        try:
            indices = labels_to_inds(labels, target_labels)
        except IndexError:
            logger.error("Failed to access indices of %s: %s.\nExisting %s: %s" %
                         (variables_name, target_labels, variables_name, labels))
            raise
    return indices


class Timeseries(object):

    logger = initialize_logger(__name__)

    ts_type = ""

    _tvb = None

    # labels_dimensions = {"space": numpy.array([]), "variables": numpy.array([])}

    def __init__(self, input=numpy.array([[], []]), **kwargs):
        if isinstance(input, (Timeseries, TimeSeries)):

            if isinstance(input, Timeseries):
                self._tvb = deepcopy(input._tvb)
                self.ts_type = str(input.ts_type)

            elif isinstance(input, TimeSeries):
                self._tvb = deepcopy(input)
                if isinstance(input, TimeSeriesRegion):
                    self.ts_type = "Region"
                if isinstance(input, TimeSeriesSEEG):
                    self.ts_type = "SEEG"
                elif isinstance(input, TimeSeriesEEG):
                    self.ts_type = "EEG"
                elif isinstance(input, TimeSeriesMEG):
                    self.ts_type = "MEG"
                elif isinstance(input, TimeSeriesEEG):
                    self.ts_type = "EEG"
                elif isinstance(input, TimeSeriesVolume):
                    self.ts_type = "Volume"
                elif isinstance(input, TimeSeriesSurface):
                    self.ts_type = "Surface"
                else:
                    self.ts_type = ""
                    warning("Input TimeSeries %s is not one of the known TVB TimeSeries classes!" % str(input))
            for attr, value in kwargs.items():
                try:
                    setattr(self, attr, value)
                except:
                    setattr(self._tvb, attr, value)

        elif isinstance(input, numpy.ndarray):
            input = prepare_4D(input, self.logger)
            time = kwargs.pop("time", None)
            if time is not None:
                start_time = float(kwargs.pop("start_time",
                                              kwargs.pop("start_time", time[0])))
                sample_period = float(kwargs.pop("sample_period",
                                                 kwargs.pop("sample_period", numpy.mean(numpy.diff(time)))))
                kwargs.update({"start_time": start_time, "sample_period": sample_period})

            # Initialize
            self.ts_type = kwargs.pop("ts_type", "Region")
            labels_ordering = kwargs.get("labels_ordering", None)

            # Get input sensors if any
            input_sensors = None
            if isinstance(kwargs.get("sensors", None), (TVBSensors, Sensors)):
                if isinstance(kwargs["sensors"], Sensors):
                    input_sensors = kwargs["sensors"]._tvb
                    self.ts_type = "%s sensor" % input_sensors.sensors_type
                    kwargs.update({"sensors": input_sensors})
                else:
                    input_sensors = kwargs["sensors"]

            # Create Timeseries
            if isinstance(input_sensors, TVBSensors) or \
                    self.ts_type in ["SEEG sensor", "Internal sensor", "EEG sensor", "MEG sensor"]:
                # ...for Sensor Timeseries
                if labels_ordering is None:
                    labels_ordering = LABELS_ORDERING
                    labels_ordering[2] = "%s sensor" % self.ts_type
                    kwargs.update({"labels_ordering": labels_ordering})
                if isinstance(input_sensors, TVBSensorsInternal) or isequal_string(self.ts_type, "Internal sensor")\
                        or isequal_string(self.ts_type, "SEEG sensor"):
                    self._tvb = TimeSeriesSEEG(data=input, **kwargs)
                    self.ts_type = "SEEG sensor"
                elif isinstance(input_sensors, TVBSensorsEEG) or isequal_string(self.ts_type, "EEG sensor"):
                    self._tvb = TimeSeriesEEG(data=input, **kwargs)
                    self.ts_type = "EEG sensor"
                elif isinstance(input_sensors, TVBSensorsMEG) or isequal_string(self.ts_type, "MEG sensor"):
                    self._tvb = TimeSeriesMEG(data=input, **kwargs)
                    self.ts_type = "MEG sensor"
                else:
                    raise_value_error("Not recognizing sensors of type %s:\n%s"
                                      % (self.ts_type, str(input_sensors)))
            else:
                input_surface = kwargs.pop("surface", None)
                if isinstance(input_surface, (Surface, TVBSurface)) or self.ts_type == "Surface":
                    self.ts_type = "Surface"
                    if isinstance(input_surface, Surface):
                        kwargs.update({"surface": input_surface._tvb})
                    else:
                        kwargs.update({"surface": input_surface})
                    if labels_ordering is None:
                        labels_ordering = LABELS_ORDERING
                        labels_ordering[2] = "Vertex"
                        kwargs.update({"labels_ordering": labels_ordering})
                    self._tvb = TimeSeriesSurface(data=input, **kwargs)
                elif isequal_string(self.ts_type, "Region"):
                    if labels_ordering is None:
                        labels_ordering = LABELS_ORDERING
                        labels_ordering[2] = "Region"
                        kwargs.update({"labels_ordering": labels_ordering})
                    self._tvb = TimeSeriesRegion(data=input, **kwargs)  # , **kwargs
                elif isequal_string(self.ts_type, "Volume"):
                    if labels_ordering is None:
                        labels_ordering = ["Time", "X", "Y", "Z"]
                        kwargs.update({"labels_ordering": labels_ordering})
                    self._tvb = TimeSeriesVolume(data=input, **kwargs)
                else:
                    self._tvb = TimeSeries(data=input, **kwargs)

            if not numpy.all([dim_label in self._tvb.labels_dimensions.keys()
                              for dim_label in self._tvb.labels_ordering]):
                warning("Lack of correspondance between timeseries labels_ordering %s\n"
                        "and labels_dimensions!: %s" % (self._tvb.labels_ordering,
                                                        self._tvb.labels_dimensions.keys()))

        self._tvb.configure()
        self.configure_time()
        self.configure_sample_rate()
        if len(self.title) == 0:
            self._tvb.title = "%s Time Series" % self.ts_type

    def duplicate(self, **kwargs):
        return self.__class__(self, **kwargs)

    def _get_indices_from_labels(self, labels, dim):
        dim_label = self.labels_ordering[dim]
        return labels_to_indices(self.labels_dimensions[dim_label], labels, dim_label, self.logger)

    def _get_indices_of_variables(self, sv_labels):
        return self._get_indices_from_labels(sv_labels, 0)

    def _get_indices_of_labels(self, list_of_labels):
        return self._get_indices_from_labels(list_of_labels, 2)

    def _get_indices_of_samples(self, list_of_labels):
        return self._get_indices_from_labels(list_of_labels, 3)

    def _get_time_for_index(self, time_index):
        return self._tvb.start_time + time_index * self._tvb.sample_period

    def _get_index_for_time(self, time_unit):
        return int((time_unit - self._tvb.start_time) / self._tvb.sample_period)

    def _check_indices(self, list_of_index, dim):
        for index in list_of_index:
            if index < 0 or index > self._tvb.data.shape[dim]:
                self.logger.error("Some of the given indices are out of region range: [0, %s]",
                                  self._tvb.data.shape[dim])
                raise IndexError

    def get_subset_by_index(self, list_of_indices, dim, **kwargs):
        assert dim in [0, 1, 2, 3]
        list_of_indices = ensure_list(list_of_indices)
        self._check_indices(list_of_indices, dim)
        slice_tuple = [slice(None), slice(None), slice(None), slice(None)]
        slice_tuple[dim] = list_of_indices
        data = self._tvb.data[tuple(slice_tuple)]
        dim_label = self.labels_ordering[dim]
        if len(self.labels_dimensions[dim_label]):
            labels_dimensions = deepcopy(self.labels_dimensions)
            labels_dimensions[dim_label] = numpy.array(labels_dimensions[dim_label])[list_of_indices]
        else:
            labels_dimensions = self.labels_dimensions
        if data.ndim == 3:
            data = numpy.expand_dims(data, 1)
        return self.duplicate(data=data, labels_dimensions=labels_dimensions, **kwargs)

    def get_subset_by_label(self, list_of_labels, dim, **kwargs):
        assert dim in [0, 1, 2, 3]
        list_of_labels = ensure_list(list_of_labels)
        dim_label = self.labels_ordering[dim]
        list_of_indices = labels_to_indices(self.labels_dimensions[dim_label], list_of_labels, dim_label, self.logger)
        return self.get_subset_by_index(list_of_indices, dim, **kwargs)

    def get_subset(self, list_of_indices_or_labels, dim, **kwargs):
        assert dim in [0, 1, 2, 3]
        list_of_indices_or_labels = ensure_list(list_of_indices_or_labels)
        if numpy.all([is_integer(ind_or_lbl) for ind_or_lbl in list_of_indices_or_labels]):
            return self.get_subset_by_index(list_of_indices_or_labels, dim, **kwargs)
        else:
            if dim == 0:
                if not numpy.all([is_numeric(ind_or_lbl) for ind_or_lbl in list_of_indices_or_labels]):
                    raise_value_error("Input consists neither of integer indices nor of points in time (floats)!: %s" %
                                      list_of_indices_or_labels)
                time_indices = [self._get_index_for_time(time) for time in list_of_indices_or_labels]
                return self.get_subset_by_index(time_indices, 0, **kwargs)
            else:
                if not numpy.all([isinstance(ind_or_lbl, string_types) for ind_or_lbl in list_of_indices_or_labels]):
                    raise_value_error("Input consists neither of integer indices nor of label strings!: %s" %
                                      list_of_indices_or_labels)
                return self.get_subset_by_label(list_of_indices_or_labels, dim, **kwargs)

    def get_times_by_index(self, list_of_times_indices, **kwargs):
        return self.get_subset_by_index(list_of_times_indices, 0, **kwargs)

    def get_times(self, list_of_times, **kwargs):
        return self.get_subset(list_of_times, 0, **kwargs)

    def get_variables_by_index(self, list_of_indices, **kwargs):
        return self.get_subset_by_index(list_of_indices, 1, **kwargs)

    def get_variables_by_label(self, list_of_labels, **kwargs):
        return self.get_subset_by_label(list_of_labels, 1, **kwargs)

    def get_variables(self, list_of_labels_or_inds, **kwargs):
        return self.get_subset(list_of_labels_or_inds, 1, **kwargs)

    def get_subspace_by_index(self, list_of_indices, **kwargs):
        return self.get_subset_by_index(list_of_indices, 2, **kwargs)

    def get_subspace_by_labels(self, list_of_labels):
        return self.get_subset_by_label(list_of_labels, 2, **kwargs)

    def get_subspace(self, list_of_labels_or_inds, **kwargs):
        return self.get_subset(list_of_labels_or_inds, 2, **kwargs)

    def get_samples_by_index(self, list_of_indices, **kwargs):
        return self.get_subset_by_index(list_of_indices, 2, **kwargs)

    def get_samples_by_labels(self, list_of_labels):
        return self.get_subset_by_label(list_of_labels, 2, **kwargs)

    def get_samples(self, list_of_labels_or_inds, **kwargs):
        return self.get_subset(list_of_labels_or_inds, 2, **kwargs)

    def __getattr__(self, attr_name):
        if self.labels_ordering[1] in self._tvb.labels_dimensions.keys():
            if attr_name in self.variables_labels:
                return self.get_variables_by_label(attr_name)
        if (self.labels_ordering[2] in self._tvb.labels_dimensions.keys()):
            if attr_name in self.space_labels:
                return self.get_subspace_by_labels(attr_name)
        if (self.labels_ordering[3] in self._tvb.labels_dimensions.keys()):
            if attr_name in self.samples_labels:
                return self.get_samples_by_labels(attr_name)
        try:
            return getattr(self._tvb, attr_name)
        except:
            # Hack to avoid stupid error messages when searching for __ attributes in numpy.array() call...
            # TODO: something better? Maybe not needed if we never do something like numpy.array(timeseries)
            if attr_name.find("__") < 0:
                self.logger.error(
                    "Attribute %s is not defined for this instance! You can use the following labels: "
                    "%s = %s and %s = %s" %
                    (attr_name, TimeseriesDimensions.VARIABLES.value, self.variables_labels,
                     TimeseriesDimensions.SPACE.value, self.space_labels))
            raise AttributeError

    def _get_index_for_slice_label(self, slice_label, slice_idx):
        if slice_idx == 1:
            return self._get_indices_of_labels([slice_label])[0]
        if slice_idx == 2:
            return self._get_indices_of_variables(slice_label)

    def _check_for_string_slice_indices(self, current_slice, slice_idx):
        slice_label1 = current_slice.start
        slice_label2 = current_slice.stop

        if isinstance(slice_label1, string_types):
            slice_label1 = self._get_index_for_slice_label(slice_label1, slice_idx)
        if isinstance(slice_label2, string_types):
            slice_label2 = self._get_index_for_slice_label(slice_label2, slice_idx)

        return slice(slice_label1, slice_label2, current_slice.step)

    def _get_string_slice_index(self, current_slice_string, slice_idx):
        return self._get_index_for_slice_label(current_slice_string, slice_idx)

    def __getitem__(self, slice_tuple):
        slice_list = []
        for idx, current_slice in enumerate(slice_tuple):
            if isinstance(current_slice, slice):
                slice_list.append(self._check_for_string_slice_indices(current_slice, idx))
            else:
                if isinstance(current_slice, string_types):
                    slice_list.append(self._get_string_slice_index(current_slice, idx))
                else:
                    slice_list.append(current_slice)

        return self._tvb.data[tuple(slice_list)]

    @property
    def title(self):
        return self._tvb.title

    @property
    def data(self):
        return self._tvb.data

    @property
    def shape(self):
        return self._tvb.data.shape

    @property
    def time(self):
        return self._tvb.time

    @property
    def time_length(self):
        return self._tvb.length_1d

    @property
    def number_of_variables(self):
        return self._tvb.length_2d

    @property
    def number_of_labels(self):
        return self._tvb.length_3d

    @property
    def number_of_samples(self):
        return self._tvb.length_4d

    @property
    def start_time(self):
        return self._tvb.start_time

    @property
    def sample_period(self):
        return self._tvb.sample_period

    @property
    def end_time(self):
        return self.start_time + (self.time_length - 1) * self.sample_period

    @property
    def duration(self):
        return self.end_time - self.start_time

    def configure_time(self):
        self._tvb.time = numpy.arange(self.start_time, self.end_time + self.sample_period, self.sample_period)
        return self

    @property
    def time_unit(self):
        return self._tvb.sample_period_unit

    @property
    def sample_period_unit(self):
        return self._tvb.sample_period_unit

    @property
    def sample_rate(self):
        return self._tvb.sample_rate

    def configure_sampling_frequency(self):
        if len(self._tvb.sample_period_unit) > 0 and self._tvb.sample_period_unit[0] == "m":
            self._tvb.sample_rate = 1000.0/self._tvb.sample_period

        else:
            self._tvb.sample_rate = 1.0/self._tvb.sample_period
        return self

    def configure_sample_rate(self):
        return self.configure_sampling_frequency()

    @property
    def labels_dimensions(self):
        return self._tvb.labels_dimensions

    @property
    def labels_ordering(self):
        return self._tvb.labels_ordering

    @property
    def space_labels(self):
        try:
            return numpy.array(self._tvb.get_space_labels())
        except:
            return numpy.array(self._tvb.labels_dimensions.get(self.labels_ordering[2], []))

    @property
    def variables_labels(self):
        return numpy.array(self._tvb.labels_dimensions.get(self.labels_ordering[1], []))

    @property
    def samples_labels(self):
        return numpy.array(self._tvb.labels_dimensions.get(self.labels_ordering[3], []))

    @property
    def nr_dimensions(self):
        return self._tvb.nr_dimensions

    @property
    def number_of_dimensions(self):
        return self._tvb.nr_dimensions

    @property
    def sensors(self):
        return self._tvb.sensors

    @property
    def connectivity(self):
        return self._tvb.connectivity

    @property
    def region_mapping_volume(self):
        return self._tvb.region_mapping_volume

    @property
    def region_mapping(self):
        return self._tvb.region_mapping

    @property
    def surface(self):
        return self._tvb.surface

    @property
    def volume(self):
        return self._tvb.volume

    @property
    def squeezed(self):
        return numpy.squeeze(self._tvb.data)

    def get_time_window(self, index_start, index_end, **kwargs):
        if index_start < 0 or index_end > self._tvb.data.shape[0]:
            self.logger.error("The time indices are outside time series interval: [%s, %s]" %
                              (0, self._tvb.data.shape[0]))
            raise IndexError
        subtime_data = self._tvb.data[index_start:index_end, :, :, :]
        if subtime_data.ndim == 3:
            subtime_data = numpy.expand_dims(subtime_data, 0)
        return self.duplicate(data=subtime_data, start_time=self._get_time_for_index(index_start), **kwargs)

    def get_time_window_by_units(self, unit_start, unit_end, **kwargs):
        end_time = self.end_time
        if unit_start < self._tvb.start_time or unit_end > end_time:
            self.logger.error("The time units are outside time series interval: [%s, %s]" %
                              (self._tvb.start_time, end_time))
            raise ValueError
        index_start = self._get_index_for_time(unit_start)
        index_end = self._get_index_for_time(unit_end)
        return self.get_time_window(index_start, index_end)

    def decimate_time(self, new_sample_period, **kwargs):
        if new_sample_period % self.sample_period != 0:
            self.logger.error("Cannot decimate time if new time step is not a multiple of the old time step")
            raise ValueError

        index_step = int(new_sample_period / self._tvb.sample_period)
        time_data = self._tvb.data[::index_step, :, :, :]
        return self.duplicate(data=time_data, sample_period=new_sample_period, **kwargs)

    def get_sample_window(self, index_start, index_end, **kwargs):
        subsample_data = self._tvb.data[:, :, :, index_start:index_end]
        if subsample_data.ndim == 3:
            subsample_data = numpy.expand_dims(subsample_data, 3)
        return self.duplicate(data=subsample_data, **kwargs)

    def get_source(self):
        if self.labels_ordering[1] not in self._tvb.labels_dimensions.keys():
            self.logger.error("No state variables are defined for this instance!")
            raise ValueError
        if PossibleVariables.SOURCE.value in self.variables_labels:
            return self.get_variables_by_label(PossibleVariables.SOURCE.value)

    def get_bipolar(self, **kwargs):
        bipolar_labels, bipolar_inds = monopolar_to_bipolar(self.space_labels)
        data = self._tvb.data[:, :, bipolar_inds[0]] - self._tvb.data[:, :, bipolar_inds[1]]
        bipolar_labels_dimensions = deepcopy(self._tvb.labels_dimensions)
        bipolar_labels_dimensions[self.labels_ordering[2]] = list(bipolar_labels)
        return self.duplicate(data=data, labels_dimensions=bipolar_labels_dimensions, **kwargs)

    def set_data(self, data):
        self._tvb.data = data
        return self

    def configure(self):
        self._tvb.configure()
        self.configure_time()
        self.configure_sampling_frequency()
        self.configure_sample_rate()
        return self


if __name__ == "__main__":

    kwargs = {"data": numpy.ones((4, 2, 10, 1)), "start_time": 0.0, "ts_type": "Region",
              "labels_dimensions": {LABELS_ORDERING[1]: ["x", "y"]}}
    ts = Timeseries(**kwargs)
    tsy = ts.y
    print(tsy.squeezed)