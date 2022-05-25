# coding=utf8
# Licensed under a 3-clause BSD style license - see LICENSE.rst
#
# Module containing some useful utility functions

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# Standard library
import warnings

# Local imports
from dysmalpy.fitting import MCMCFitter, MPFITFitter

# Third party imports
import numpy as np
import astropy.units as u


def _model_aperture_r(model, model_key_re = ['disk+bulge','r_eff_disk']):
    # Default: use old behavior of model_key_re = ['disk+bulge','r_eff_disk']:

    comp = model.components.__getitem__(model_key_re[0])
    param_i = comp.param_names.index(model_key_re[1])
    r_eff = comp.parameters[param_i]

    return r_eff




class ConfigBase:
    """
    Base class to handle settings for different functions.
    """

    def __init__(self, **kwargs):
        self.set_defaults()
        self.fill_values(**kwargs)

    def set_defaults(self):
        raise ValueError("Must be set for each inheriting class!")

    def fill_values(self, **kwargs):
        for key in self.__dict__.keys():
            if key in kwargs.keys():
                self.__dict__[key] = kwargs[key]

    @property
    def dict(self):
        return self.to_dict()

    def to_dict(self):
        kwarg_dict = {}
        for key in self.__dict__.keys():
            kwarg_dict[key] = self.__dict__[key]
        return kwarg_dict

#
# class Config_create_model_data(ConfigBase):
#     """
#     Class to handle settings for Galaxy.create_model_data.
#     """
#     def __init__(self, **kwargs):
#
#         super(Config_create_model_data, self).__init__(**kwargs)
#
#     def set_defaults(self):
#         self.ndim_final = 3
#         self.line_center = None
#         self.aper_centers = None
#         self.slit_width = None
#         self.slit_pa = None
#         self.profile1d_type = None
#         self.from_instrument = True
#         self.from_data = True
#         self.aperture_radius = None
#         self.pix_perp = None
#         self.pix_parallel = None
#         self.pix_length = None
#         self.skip_downsample = False
#         self.partial_aperture_weight = False
#         #self.partial_weight = False   ## used for rot curve plotting -- but only passed to aperture
#         self.gauss_extract_with_c = True # True or False or None, whether to use faster C++ 1d gaussian spectral fitting.
#         # Default always try to use the C++ gaussian fitter
#
#
# class Config_simulate_cube(ConfigBase):
#     """
#     Class to handle settings for model_set.simulate_cube
#     """
#     def __init__(self, **kwargs):
#         super(Config_simulate_cube, self).__init__(**kwargs)
#
#     def set_defaults(self):
#         self.nx_sky = None
#         self.ny_sky = None
#         self.rstep = None
#         self.spec_type = 'velocity'
#         self.spec_step = 10.
#         self.spec_start = -1000.
#         self.nspec = 201
#         self.spec_unit = (u.km/u.s)
#         self.xcenter = None
#         self.ycenter = None
#         self.oversample = 1
#         self.oversize = 1
#         self.transform_method = 'direct'
#         self.zcalc_truncate = None     # Default will be set in galaxy.create_model_data:
#                                        #    0D/1D/2D/3D: True/True/False/False
#                                        #    because for the smaller spatial extent of a single spaxel
#                                        #    for 2D/3D leads to asymmetries from truncation,
#                                        #    while this is less important for 0D/1D (combo in apertures).
#                                        #    Previous: True
#         self.n_wholepix_z_min = 3
#         self.lensing_datadir = None # datadir for the lensing model mesh.dat
#         self.lensing_mesh = None # lensing model mesh.dat
#         self.lensing_ra = None # lensing model ref ra
#         self.lensing_dec = None # lensing model ref dec
#         self.lensing_sra = None # lensing source plane image center ra
#         self.lensing_sdec = None # lensing source plane image center dec
#         self.lensing_ssizex = None # lensing source plane image size in x
#         self.lensing_ssizey = None # lensing source plane image size in y
#         self.lensing_spixsc = None # lensing source plane image pixel size in arcsec unit
#         self.lensing_imra = None # lensing image plane image center ra
#         self.lensing_imdec = None # lensing image plane image center dec
#         self.lensing_transformer = None # a placeholder for the object pointer
#
#



class ConfigFitBase(ConfigBase):
    """
    Class to handle settings for fitting.fit_mcmc
    """
    def __init__(self, **kwargs):
        super(ConfigFitBase, self).__init__(**kwargs)


    def fill_values(self, **kwargs):
        super(ConfigFitBase, self).fill_values(**kwargs)
        # Backwards compatibility:
        if (('model_key_re' in kwargs.keys()) & ('model_aperture_r' not in kwargs.keys()) \
            & ('model_key_re' not in self.__dict__.keys())):
            self.model_aperture_r = (lambda modelset: _model_aperture_r(modelset, model_key_re=self.model_key_re))

    def set_defaults(self):
        # Fitting defaults that are shared between all fitting methods

        self.fitvelocity = True
        self.fitdispersion = True
        self.fitflux = False

        self.blob_name = None

        self.model_aperture_r = _model_aperture_r
        self.model_key_halo=['halo']

        self.save_model = True
        self.save_model_bestfit = True
        self.save_bestfit_cube=True
        self.save_data = True
        self.save_vel_ascii = True
        self.save_results = True

        self.overwrite = False

        self.f_model = None
        self.f_model_bestfit = None
        self.f_cube = None
        self.f_plot_bestfit = None

        # Specific to 3D: 'f_plot_spaxel', 'f_plot_aperture', 'f_plot_channel'
        self.f_plot_spaxel = None
        self.f_plot_aperture = None
        self.f_plot_channel = None

        self.f_results = None

        self.f_vel_ascii = None
        self.f_vcirc_ascii = None
        self.f_mass_ascii = None
        self.f_log = None

        self.do_plotting = True
        self.plot_type = 'pdf'


class Config_fit_mcmc(ConfigFitBase):
    """
    Class to handle settings for fitting.fit_mcmc
    """
    def __init__(self, **kwargs):
        self.set_mcmc_defaults()
        super(Config_fit_mcmc, self).__init__(**kwargs)

    def set_mcmc_defaults(self):
        # MCMC specific defaults
        self.nWalkers = 10
        self.nCPUs = 1
        self.cpuFrac = None
        self.scale_param_a = 3.
        self.nBurn = 2.
        self.nSteps = 10.
        self.minAF = 0.2
        self.maxAF = 0.5
        self.nEff = 10
        self.oversampled_chisq = True
        self.red_chisq = False

        self.save_burn = False

        self.outdir = 'mcmc_fit_results/'
        self.save_intermediate_sampler_chain = True
        self.nStep_intermediate_save = 5
        self.continue_steps = False

        self.nPostBins = 50
        self.linked_posterior_names = None

        self.input_sampler = None

        self.f_sampler = None
        self.f_sampler_tmp = None
        self.f_burn_sampler = None
        self.f_chain_ascii = None

        self.f_plot_trace_burnin = None
        self.f_plot_trace = None
        self.f_plot_param_corner = None

class Config_fit_mpfit(ConfigFitBase):
    """
    Class to handle settings for fitting.fit_mcmc
    """
    def __init__(self, **kwargs):
        self.set_mpfit_defaults()
        super(Config_fit_mpfit, self).__init__(**kwargs)

    def set_mpfit_defaults(self):
        # MPFIT specific defaults

        self.use_weights=False
        self.maxiter=200

        self.outdir='mpfit_fit_results/'


class OutputOptions:
    """
    Class to hold all options for file output during and after fitting
    """

    def __init__(outdir='./',
                 save_model=True,
                 save_model_bestfit=True,
                 save_bestfit_cube=True,
                 save_data=True,
                 save_vel_ascii=True,
                 save_results=True,
                 file_base=None,
                 do_plotting=True,
                 plot_type='pdf',
                 overwrite=False
                 ):

        self.outdir = outdir
        self.save_model = save_model
        self.save_model_bestfit = save_model_bestfit
        self.save_bestfit_cube = save_bestfit_cube
        self.save_data = save_data
        self.save_vel_ascii = save_vel_ascii
        self.save_results = save_results
        self.file_base = file_base
        self.do_plotting = do_plotting
        self.plot_type = plot_type
        self.overwrite=overwrite

        # Galaxy specific filenames
        self.f_model = None
        self.f_vcirc_ascii = None
        self.f_mass_ascii = None
        self.f_results = None
        self.f_plot_bestfit = None

        # Observation and tracer specific filenames
        self.f_model_bestfit = OrderedDict()
        self.f_bestfit_cube = OrderedDict()
        self.f_vel_ascii = OrderedDict()

        # MCMC fitting specific filenames
        self.f_sampler_continue = None
        self.f_sampler = None
        self.f_sampler_tmp = None
        self.f_burn_sampler = None
        self.f_plot_trace_burnin = None
        self.f_plot_trace = None
        self.f_plot_param_corner = None
        self.f_chain_ascii = None


    def set_output_options(self, gal, fitter):

        if isinstance(fitter, MCMCFitter):
            fit_type = 'mcmc'
        elif isinstance(fitter, MPFITFitter):
            fit_type = 'mpfit'
        else:
            raise ValueError("Unrecognized Fitter!")

        if self.file_base is None:
            self.file_base = gal.name

        if self.file_base[-1] == '_':
            self.file_base = self.file_base[0:]

        if self.save_model:
            self.f_model = "{}{}_model.pickle".format(self.outdir,self.file_base)

        if self.save_model_besfit:

            for obs_name in gal.observations:

                obs = gal.observations[obs_name]

                if obs.data.ndim == 1:
                    self.f_model_bestfit[obs_name] = "{}{}_{}_{}".format(self.outdir, self.file_base, obs_name, 'out-1dplots.txt')
                elif obs.data.ndim == 2:
                    self.f_model_bestfit[obs_name] = "{}{}_{}_{}".format(self.outdir, self.file_base, obs_name, 'out-velmaps.fits')
                elif obs.data.ndim == 3:
                    self.f_model_bestfit[obs_name] = "{}{}_{}_{}".format(self.outdir, self.file_base, obs_name, 'out-cube.fits')
                elif obs.data.ndim == 0:
                    self.f_model_bestfit[obs_name] = "{}{}_{}_{}".format(self.outdir, self.file_base, obs_name,'out-0d.txt')

        if self.save_bestfit_cube:

            for obs_name in gal.observations:

                obs = gal.observations[obs_name]
                f_bestfit_cube[obs_name] = "{}{}_{}_bestfit_cube.fits".format(self.outdir, self.file_base, obs_name)

        if self.save_vel_ascii:

            self.f_vcirc_ascii = "{}{}_bestfit_vcirc.dat".format(self.outdir,self.file_base)
            self.f_mass_ascii = "{}{}_bestfit_menc.dat".format(self.outdir,self.file_base)


            for tracer in gal.model.dispersions:

                self.f_vel_ascii[tracer] = "{}{}_{}_{}".format(self.outdir, self.file_base, tracer, 'bestfit_velprofile.dat')

        if self.save_results:

            self.f_results = "{}{}_{}_results.pickle".format(self.outdir, self.file_base, fit_type)

        if self.do_plotting:

            self.f_plot_bestfit = "{}{}_{}_bestfit.{}".format(self.outdir, self.file_base, fit_type, self.plot_type)

        if fit_type == 'mcmc':

            if fitter._emcee_version < 3:
                self._set_mcmc_filenames_221()
            else:
                self._set_mcmc_filenames_3()

    def _set_mcmc_filenames_221(self):

        self.f_sampler_continue = self.outdir+self.file_base+'_mcmc_sampler_continue.pickle'
        self.f_sampler = self.outdir+self.file_base+'_mcmc_sampler.pickle'
        self.f_sampler_tmp = self.outdir+self.file_base+'_mcmc_sampler_INPROGRESS.pickle'
        self.f_burn_sampler = self.outdir+self.file_base+'_mcmc_burn_sampler.pickle'
        self.f_plot_trace_burnin = self.outdir+self.file_base+'_mcmc_burnin_trace.{}'.format(self.plot_type)
        self.f_plot_trace = self.outdir+self.file_base+'_mcmc_trace.{}'.format(self.plot_type)
        self.f_plot_param_corner = self.outdir+self.file_base+'_mcmc_param_corner.{}'.format(self.plot_type)
        self.f_chain_ascii = self.outdir+self.file_base+'_mcmc_chain_blobs.dat'

    def _set_mcmc_filenames_3(self):

        ftype_sampler = 'h5'
        self.f_sampler = self.outdir+self.file_base+'_mcmc_sampler.{}'.format(ftype_sampler)
        self.f_plot_trace_burnin = self.outdir+self.file_base+'_mcmc_burnin_trace.{}'.format(self.plot_type)
        self.f_plot_trace = self.outdir+self.file_base+'_mcmc_trace.{}'.format(self.plot_type)
        self.f_plot_param_corner = self.outdir+self.file_base+'_mcmc_param_corner.{}'.format(self.plot_type)
        self.f_chain_ascii = oself.outdir+self.file_base+'_mcmc_chain_blobs.dat'
