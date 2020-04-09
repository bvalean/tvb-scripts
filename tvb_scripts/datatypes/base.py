from copy import deepcopy

from tvb.basic.neotraits.api import HasTraits

from tvb_scripts.utils.data_structures_utils import labels_to_inds
from tvb_scripts.utils.log_error_utils import warning


class BaseModel(HasTraits):

    def set_attributes(self, **kwargs):
        for attr, value in kwargs.items():
            try:
                if len(value):
                    setattr(self, attr, value)
            except:
                warning("Failed to set attribute %s to %s!" % (attr, self.__class__.__name__))
        return self

    @staticmethod
    def from_instance(instance, **kwargs):
        result = deepcopy(instance)
        result = result.set_attributes(result, **kwargs)
        result.configure()
        return result

    @classmethod
    def from_tvb_instance(cls, instance, **kwargs):
        result = cls()
        attributes = instance.__dict__
        attributes.update(**kwargs)
        result = result.set_attributes(result, attributes)
        result.configure()
        return result

    @classmethod
    def from_tvb_file(cls, filepath, **kwargs):
        kwargs["filepath"] = filepath
        result = cls.from_tvb_instance(cls.from_file(filepath), **kwargs)
        return result

    @staticmethod
    def labels2inds(all_labels, labels):
        return labels_to_inds(all_labels, labels)
