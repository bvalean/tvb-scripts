# coding=utf-8
"""
Read VEP related entities from TVB format (tvb_data module) and data-structures
"""
import os
from collections import OrderedDict
import numpy as np
from tvb.basic.profile import TvbProfile

TvbProfile.set_profile(TvbProfile.LIBRARY_PROFILE)


from tvb.datatypes import connectivity, surfaces, region_mapping, sensors, structural, projections

from tvb_utils.log_error_utils import initialize_logger
from tvb_utils.data_structures_utils import ensure_list
from tvb_head.model.surface import Surface
from tvb_head.model.sensors import Sensors
from tvb_head.model.connectivity import Connectivity
from tvb_head.model.head import Head


class TVBReader(object):
    logger = initialize_logger(__name__)

    def read_connectivity(self, path):
        tvb_conn = connectivity.Connectivity.from_file(path)
        return Connectivity(path, tvb_conn.weights, tvb_conn.tract_lengths,
                            tvb_conn.region_labels, tvb_conn.centres,
                            tvb_conn.hemispheres, tvb_conn.orientations, tvb_conn.areas)

    def read_cortical_surface(self, path):
        if os.path.isfile(path):
            tvb_srf = surfaces.CorticalSurface.from_file(path)
            return Surface(tvb_srf.vertices, tvb_srf.triangles,
                           tvb_srf.vertex_normals, tvb_srf.triangle_normals)
        else:
            self.logger.warning("\nNo Cortical Surface file found at path " + path + "!")
            return []

    def read_region_mapping(self, path):
        if os.path.isfile(path):
            tvb_rm = region_mapping.RegionMapping.from_file(path)
            return tvb_rm.array_data
        else:
            self.logger.warning("\nNo Region Mapping file found at path " + path + "!")
            return []

    def read_volume_mapping(self, path):
        if os.path.isfile(path):
            tvb_vm = region_mapping.RegionVolumeMapping.from_file(path)
            return tvb_vm.array_data
        else:
            self.logger.warning("\nNo Volume Mapping file found at path " + path + "!")
            return []

    def read_t1(self, path):
        if os.path.isfile(path):
            tvb_t1 = structural.StructuralMRI.from_file(path)
            return tvb_t1.array_data
        else:
            self.logger.warning("\nNo Structural MRI file found at path " + path + "!")
            return []

    def read_sensors(self, filename, root_folder, s_type, atlas=""):

        def get_sensors_name(sensors_file, s_type):
            locations_file = sensors_file[0]
            if len(sensors_file) > 1:
                gain_file = sensors_file[1]
            else:
                gain_file = ""
            return s_type.value + (locations_file + gain_file).replace(".txt", "").replace(s_type.value, "")

        filename = ensure_list(filename)
        name = get_sensors_name(filename, s_type)
        path = os.path.join(root_folder, filename[0])
        if os.path.isfile(path):
            if s_type == Sensors.TYPE_EEG:
                tvb_sensors = sensors.SensorsEEG.from_file(path)
            elif s_type == Sensors.TYPE_MEG:
                tvb_sensors = sensors.SensorsMEG.from_file(path)
            else:
                tvb_sensors = sensors.SensorsInternal.from_file(path)
            if len(filename) > 1:
                gain_matrix = self.read_gain_matrix(os.path.join(root_folder, atlas, filename[1]), s_type, atlas)
            else:
                gain_matrix = np.array([])
            return Sensors(tvb_sensors.labels, tvb_sensors.locations, orientations=tvb_sensors.orientations,
                           gain_matrix=gain_matrix, s_type=s_type, name=name)
        else:
            self.logger.warning("\nNo Sensor file found at path " + path + "!")
            return None

    def read_gain_matrix(self, path, s_type):
        if os.path.isfile(path):
            if s_type == Sensors.TYPE_EEG:
                tvb_prj = projections.ProjectionSurfaceEEG.from_file(path)
            elif s_type == Sensors.TYPE_MEG:
                tvb_prj = projections.ProjectionSurfaceMEG.from_file(path)
            else:
                tvb_prj = projections.ProjectionSurfaceSEEG.from_file(path)
            return tvb_prj.gain_matrix_data
        else:
            self.logger.warning("\nNo Projection Matrix file found at path " + path + "!")
            return None

    def read_head(self, root_folder, name='', atlas="default",
                  connectivity_file="connectivity.zip",
                  cortical_surface_file="surface_cort.zip",
                  subcortical_surface_file="surface_subcort.zip",
                  cortical_region_mapping_file="region_mapping_cort.txt",
                  subcortical_region_mapping_file="region_mapping_subcort.txt",
                  eeg_sensors_files=[("eeg_brainstorm_65.txt", "gain_matrix_eeg_65_surface_16k.npy")],
                  meg_sensors_files=[("meg_brainstorm_276.txt", "gain_matrix_meg_276_surface_16k.npy")],
                  seeg_sensors_files=[("seeg_xyz.txt", "seeg_dipole_gain.txt"),
                                      ("seeg_xyz.txt", "seeg_distance_gain.txt"),
                                      ("seeg_xyz.txt", "seeg_regions_distance_gain.txt"),
                                      ("seeg_588.txt", "gain_matrix_seeg_588_surface_16k.npy")],
                  vm_file="aparc+aseg.nii.gz", t1_file="T1.nii.gz",
                  ):

        conn = self.read_connectivity(os.path.join(root_folder, atlas, connectivity_file))
        cort_srf = self.read_cortical_surface(os.path.join(root_folder, cortical_surface_file))
        subcort_srf = self.read_cortical_surface(os.path.join(root_folder, subcortical_surface_file))
        cort_rm = self.read_region_mapping(os.path.join(root_folder, atlas, cortical_region_mapping_file))
        subcort_rm = self.read_region_mapping(os.path.join(root_folder, atlas, subcortical_region_mapping_file))
        vm = self.read_volume_mapping(os.path.join(root_folder, atlas, vm_file))
        t1 = self.read_t1(os.path.join(root_folder, t1_file))
        sensorsSEEG = OrderedDict()
        for s_files in ensure_list(seeg_sensors_files):
            sensors = self.read_sensors(s_files, root_folder, Sensors.TYPE_SEEG, atlas)
            sensorsSEEG[sensors.name] = sensors
        sensorsEEG = OrderedDict()
        for s_files in ensure_list(eeg_sensors_files):
            sensors = self.read_sensors(s_files, root_folder, Sensors.TYPE_EEG, atlas)
            sensorsSEEG[sensors.name] = sensors
        sensorsMEG =  OrderedDict()
        for s_files in ensure_list(meg_sensors_files):
            sensors = self.read_sensors(s_files, root_folder, Sensors.TYPE_MEG, atlas)
            sensorsSEEG[sensors.name] = sensors
        if len(name) == 0:
            name = atlas
        return Head(conn, cort_srf, subcort_srf, cort_rm, subcort_rm, vm, t1, name,
                    sensorsSEEG=sensorsSEEG, sensorsEEG=sensorsEEG, sensorsMEG=sensorsMEG)
