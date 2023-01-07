# coding=utf8
# Licensed under a 3-clause BSD style license - see LICENSE.rst
#
# Classes and functions for fitting DYSMALPY kinematic models
#   to the observed data using Nested sampling, with Dynesty:
#   Speagle 2020, https://ui.adsabs.harvard.edu/abs/2020MNRAS.493.3132S/abstract
#   dynesty.readthedocs.io

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

## Standard library
import logging
from multiprocess import cpu_count, Pool

# DYSMALPY code
from dysmalpy.data_io import load_pickle, dump_pickle, pickle_module
from dysmalpy import plotting
from dysmalpy import galaxy
# from dysmalpy.utils import fit_uncertainty_ellipse
# from dysmalpy import utils_io as dpy_utils_io
from dysmalpy import utils as dpy_utils
from dysmalpy.fitting import base
from dysmalpy.fitting import utils as fit_utils

# Third party imports
import os
import numpy as np
from collections import OrderedDict
import astropy.units as u
import copy

import dynesty
import dynesty.utils
dynesty.utils.pickle_module = pickle_module


import time, datetime


__all__ = ['NestedFitter', 'NestedResults']


# LOGGER SETTINGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('DysmalPy')



class NestedFitter(base.Fitter):
    """
    Class to hold the Nested sampling fitter attributes + methods
    """
    def __init__(self, **kwargs):

        self._set_defaults()
        super(NestedFitter, self).__init__(fit_method='Nested', **kwargs)

    def _set_defaults(self):
        # Nested sampling specific defaults
        self.maxiter=None

        self.bound = 'multi'
        self.sample = 'unif'

        self.nlive_init = 100
        self.nlive_batch = 100
        self.use_stop = False
        self.pfrac = 1.0

        self.nCPUs = 1.0
        self.cpuFrac = None

        self.oversampled_chisq = True

        self.nPostBins = 50
        self.linked_posterior_names = None



    def fit(self, gal, output_options):
        """
        Fit observed kinematics using nested sampling and a DYSMALPY model set.

        Parameters
        ----------
            gal : `Galaxy` instance
                observed galaxy, including kinematics.
                also contains instrument the galaxy was observed with (gal.instrument)
                and the DYSMALPY model set, with the parameters to be fit (gal.model)

            output_options : `config.OutputOptions` instance
                instance holding ouptut options for nested sampling fitting.

        Returns
        -------
            nestedResults : `NestedResults` instance
                NestedResults class instance containing the bestfit parameters, sampler_results information, etc.
        """

        # --------------------------------
        # Check option validity:

        # # Temporary: testing:
        # if self.red_chisq:
        #     raise ValueError("red_chisq=True is currently *DISABLED* to test lnlike impact vs lnprior")

        # Check the FOV is large enough to cover the data output:
        dpy_utils._check_data_inst_FOV_compatibility(gal)

        # Pre-calculate instrument kernels:
        gal = dpy_utils._set_instrument_kernels(gal)

        # --------------------------------
        # Basic setup:

        # For compatibility with Python 2.7:
        mod_in = copy.deepcopy(gal.model)
        gal.model = mod_in

        #if nCPUs is None:
        if self.cpuFrac is not None:
            self.nCPUs = int(np.floor(cpu_count()*self.cpuFrac))

        # +++++++++++++++++++++++
        # Setup for oversampled_chisq:
        if self.oversampled_chisq:
            gal = fit_utils.setup_oversampled_chisq(gal)
        # +++++++++++++++++++++++

        # Set output options: filenames / which to save, etc
        output_options.set_output_options(gal, self)

        # MUST INCLUDE NESTED-SPECIFICS NOW!
        fit_utils._check_existing_files_overwrite(output_options, 
                                                  fit_type='nested', 
                                                  fitter=self)

        # --------------------------------
        # Setup file redirect logging:
        if output_options.f_log is not None:
            loggerfile = logging.FileHandler(output_options.f_log)
            loggerfile.setLevel(logging.INFO)
            logger.addHandler(loggerfile)

        # ++++++++++++++++++++++++++++++++
        # Run Dynesty:

        # Keywords for log likelihood:
        logl_kwargs = {'gal': gal, 
                       'fitter': self} 

        # Keywords for prior transform:
        # This needs to include the gal object, 
        #   so we can get the appropriate per-free-param priors
        ptform_kwargs = {'gal': gal}

        ndim = gal.model.nparams_free

        # Set blob switch for Dynesty:
        if self.blob_name is not None:
            _calc_blob = True
        else:
            _calc_blob = False

        # --------------------------------
        # Start pool
        if (self.nCPUs > 1):
            pool = Pool(self.nCPUs)
            queue_size = self.nCPUs
        else:
            pool = queue_size = None

        

        dsampler_results = dynesty.DynamicNestedSampler(log_like_dynesty,
                                                prior_transform_dynsety,
                                                ndim,
                                                bound=self.bound,
                                                sample=self.sample,
                                                logl_kwargs=logl_kwargs,
                                                ptform_kwargs=ptform_kwargs, 
                                                blob=_calc_blob, 
                                                pool=pool,
                                                queue_size=queue_size)

        dsampler_results.run_nested(nlive_init=self.nlive_init,
                            nlive_batch=self.nlive_batch,
                            maxiter=self.maxiter,
                            use_stop=self.use_stop,
                            checkpoint_file=output_options.f_checkpoint, 
                            wt_kwargs={'pfrac': self.pfrac})

        res = dsampler_results.results

        if output_options.f_sampler_results is not None:
            # Save stuff to file, for future use:
            dump_pickle(res, filename=output_options.f_sampler_results, 
                        overwrite=output_options.overwrite)




        # --------------------------------
        # Bundle the results up into a results class:
        nestedResults = NestedResults(model=gal.model, sampler_results=res,
                    linked_posterior_names=self.linked_posterior_names,
                    blob_name=self.blob_name,
                    nPostBins=self.nPostBins)

        if self.oversampled_chisq:
            nestedResults.oversample_factor_chisq = OrderedDict()
            for obs_name in gal.observations:
                obs = gal.observations[obs_name]
                nestedResults.oversample_factor_chisq[obs_name] = obs.data.oversample_factor_chisq

        # Do all analysis, plotting, saving:
        nestedResults.analyze_plot_save_results(gal, output_options=output_options)

        # --------------------------------
        # Clean up logger:
        if output_options.f_log is not None:
            logger.removeHandler(loggerfile)

        return nestedResults





class NestedResults(base.BayesianFitResults, base.FitResults):
    """
    Class to hold results of nested sampling fitting to DYSMALPY models.

    Note: the dynesty *Results* object (containing the results of the run) 
          is stored in nestedResults.sampler_results

        The name of the free parameters in the chain are accessed through:
            nestedResults.chain_param_names,
                or more generally (separate model + parameter names) through
                nestedResults.free_param_names

        Optional attribute:
        linked_posterior_names: indicate if best-fit of parameters
                                should be measured in multi-D histogram space
                                format: set of linked parameter sets, with each linked parameter set
                                        consisting of len-2 tuples/lists of the
                                        component+parameter names.


        Structure explanation:
        (1) Want to analyze component+param 1 and 2 together, and then
            3 and 4 together.

            Input structure would be:
                linked_posterior_names = [ joint_param_bundle1, joint_param_bundle2 ]
                with
                join_param_bundle1 = [ [cmp1, par1], [cmp2, par2] ]
                jont_param_bundle2 = [ [cmp3, par3], [cmp4, par4] ]
                for a full array of:
                linked_posterior_names =
                    [ [ [cmp1, par1], [cmp2, par2] ], [ [cmp3, par3], [cmp4, par4] ] ]

        (2) Want to analyze component+param 1 and 2 together:
            linked_posterior_names = [ joint_param_bundle1 ]
            with
            join_param_bundle1 = [ [cmp1, par1], [cmp2, par2] ]

            for a full array of:
                linked_posterior_names = [ [ [cmp1, par1], [cmp2, par2] ] ]

                eg: look at halo: mvirial and disk+bulge: total_mass together
                    linked_posterior_names = [[['halo', 'mvirial'], ['disk+bulge', 'total_mass']]]
                    or linked_posterior_names = [[('halo', 'mvirial'), ('disk+bulge', 'total_mass')]]



    """
    def __init__(self, model=None, sampler_results=None,
                 linked_posterior_names=None,
                 blob_name=None, nPostBins=50):

        # self.sampler_results = sampler_results

        # # Set up samples, and blobs if blob_name != None
        # self._setup_samples_blobs()

        # self.linked_posterior_names = linked_posterior_names
        # self.nPostBins = nPostBins

        super(NestedResults, self).__init__(model=model, blob_name=blob_name,
                                            fit_method='Nested', 
                                            linked_posterior_names=linked_posterior_names, 
                                            sampler_results=sampler_results, nPostBins=nPostBins)

    def __setstate__(self, state):
        # Compatibility hacks
        super(NestedResults, self).__setstate__(state)

        # ---------
        if 'sampler' in state.keys():
            self._setup_samples_blobs()


    def _setup_samples_blobs(self):

        # Extract weighted samples, as in 
        # https://dynesty.readthedocs.io/en/v1.2.3/quickstart.html?highlight=resample_equal#basic-post-processing
        
        samples_unweighted = self.sampler_results.samples 
        blobs_unweighted = self.sampler_results.blob
        
        # weights = np.exp(self.sampler.logwt - self.sampler.logz[-1])

        # Updated, see https://dynesty.readthedocs.io/en/v2.0.3/quickstart.html#basic-post-processing
        weights = self.sampler_results.importance_weights()

        samples = dynesty.utils.resample_equal(samples_unweighted, weights)

        # Check if blobs_unweighted is None?
        blobs = dynesty.utils.resample_equal(blobs_unweighted, weights)

        self.sampler = base.BayesianSampler(samples=samples, blobs=blobs, 
                                            weights=weights, 
                                            samples_unweighted=samples_unweighted, 
                                            blobs_unweighted=blobs_unweighted)

    def plot_run(self, fileout=None, overwrite=False):
        """Plot/replot the trace for the Bayesian fitting"""
        plotting.plot_run(self, fileout=fileout, overwrite=overwrite)

    def reload_sampler_results(self, filename=None):
        """Reload the Nested sampling results saved earlier"""
        if filename is None:
            filename = self.f_sampler_results

        #hdf5_aliases = ['h5', 'hdf5']
        pickle_aliases = ['pickle', 'pkl', 'pcl']
        # if (filename.split('.')[-1].lower() in hdf5_aliases):
        #     self.sampler_results = _reload_sampler_results_hdf5(filename=filename)

        # elif (filename.split('.')[-1].lower() in pickle_aliases):
        if (filename.split('.')[-1].lower() in pickle_aliases):
            self.sampler_results = _reload_sampler_results_pickle(filename=filename)



def log_like_dynesty(theta, gal=None, fitter=None):

    # Update the parameters
    gal.model.update_parameters(theta)

    # Update the model data
    gal.create_model_data()

    # Evaluate likelihood prob of theta
    llike = base.log_like(gal, fitter=fitter)

    return llike


def prior_transform_dynsety(u, gal=None):
    """
    From Dynesty documentation: 
    Transforms the uniform random variables `u ~ Unif[0., 1.)`
    to the parameters of interest.
    """
    # NEEDS TO BE IN ORDER OF THE VARIABLES 
    # -- which means we need to construct this from the gal.model method

    v = gal.model.get_prior_transform(u)

    return v



def _reload_sampler_results_pickle(filename=None):
    return load_pickle(filename)



def _reload_all_fitting_nested(filename_galmodel=None, filename_results=None):
    gal = galaxy.load_galaxy_object(filename=filename_galmodel)
    results = NestedResults()
    results.reload_results(filename=filename_results)
    return gal, results

