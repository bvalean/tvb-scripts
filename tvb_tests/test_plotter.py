# -*- coding: utf-8 -*-

import os
from tvb_plot.plotter import Plotter
from tvb_tests.base import BaseTest


class TestPlotter(BaseTest):
    plotter = Plotter(BaseTest.config)

    def test_plot_head(self):
        head = self._prepare_dummy_head()
        # TODO: this filenames may change because they are composed inside the plotting functions
        filename1 = "Connectivity_.png"
        filename2 = "HeadStats.png"
        filename3 = "1-SEEG-Projection.png"

        assert not os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename1))
        assert not os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename2))
        assert not os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename3))

        self.plotter.plot_head(head)

        assert os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename1))
        assert os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename2))
        # Because there is no gain matrix
        assert not os.path.exists(os.path.join(self.config.out.FOLDER_FIGURES, filename3))
