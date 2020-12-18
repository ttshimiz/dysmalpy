# Script to fit single object in 1D with Dysmalpy

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import platform
from contextlib import contextmanager
import sys
import shutil

import matplotlib
matplotlib.use('agg')

from dysmalpy import galaxy
from dysmalpy import models
from dysmalpy import fitting
from dysmalpy import instrument
from dysmalpy import parameters
from dysmalpy import plotting
from dysmalpy import config

import copy
import numpy as np
import astropy.units as u

# from dysmalpy.fitting_wrappers import utils_io
# from dysmalpy.fitting_wrappers.plotting import plot_bundle_1D
# from dysmalpy.fitting_wrappers.dysmalpy_fit_single import dysmalpy_fit_single

try:
    import utils_io
    from plotting import plot_bundle_1D
    from dysmalpy_fit_single import dysmalpy_fit_single
except ImportError:
    from . import utils_io
    from .plotting import plot_bundle_1D
    from .dysmalpy_fit_single import dysmalpy_fit_single


# Backwards compatibility
def dysmalpy_fit_single_1D(param_filename=None, data=None, datadir=None,
             outdir=None, plot_type='pdf', overwrite=None):
     return dysmalpy_fit_single(param_filename=param_filename, data=data, datadir=datadir,
                 outdir=outdir, plot_type=plot_type, overwrite=overwrite)


def dysmalpy_reanalyze_single_1D(param_filename=None, data=None, datadir=None, outdir=None, plot_type='pdf'):

    # Read in the parameters from param_filename:
    params = utils_io.read_fitting_params(fname=param_filename)

    # OVERRIDE SETTINGS FROM PARAMS FILE if passed directly -- eg from an example Jupyter NB:
    if datadir is not None:
        params['datadir'] = datadir
    if outdir is not None:
        params['outdir'] = outdir

    # Setup some paths:
    outdir = utils_io.ensure_path_trailing_slash(params['outdir'])
    params['outdir'] = outdir

    fitting.ensure_dir(params['outdir'])

    if 'plot_type' not in params.keys():
        params['plot_type'] = plot_type
    else:
        plot_type = params['plot_type']

    # Check if fitting already done:
    if params['fit_method'] == 'mcmc':
        # Copy paramfile that is OS independent
        shutil.copy(param_filename, outdir)

        # Reload the results, etc
        #######################
        # Reload stuff
        galtmp, fit_dict = utils_io.setup_single_object_1D(params=params, data=data)


        config_c_m_data = config.Config_create_model_data(**fit_dict)
        config_sim_cube = config.Config_simulate_cube(**fit_dict)
        kwargs_galmodel = {**config_c_m_data.dict, **config_sim_cube.dict}

        gal, results = fitting.reload_all_fitting(filename_galmodel=fit_dict['f_model'],
                                    filename_results=fit_dict['f_mcmc_results'],
                                    fit_method=params['fit_method'])

        # Do all analysis, plotting, saving:
        results.analyze_plot_save_results(gal,
                      blob_name=fit_dict['blob_name'],
                      linked_posterior_names=fit_dict['linked_posterior_names'],
                      model_key_re=fit_dict['model_key_re'],
                      model_key_halo=fit_dict['model_key_halo'],
                      fitdispersion=fit_dict['fitdispersion'],
                      fitflux=fit_dict['fitflux'],
                      f_model=fit_dict['f_model'],
                      f_model_bestfit=fit_dict['f_model_bestfit'],
                      f_vel_ascii = fit_dict['f_vel_ascii'],
                      save_data=True,
                      save_bestfit_cube=True,
                      f_cube=fit_dict['f_cube'],
                      do_plotting = fit_dict['do_plotting'],
                      plot_type=plot_type,
                      **kwargs_galmodel)

        # Reload fitting stuff to get the updated gal object
        gal, results = fitting.reload_all_fitting(filename_galmodel=fit_dict['f_model'],
                                    filename_results=fit_dict['f_mcmc_results'],
                                    fit_method=params['fit_method'])

        # Save results
        utils_io.save_results_ascii_files(fit_results=results, gal=gal, params=params,
                        overwrite=overwrite)

    elif params['fit_method'] == 'mpfit':
        galtmp, fit_dict = utils_io.setup_single_object_1D(params=params, data=data)

        config_c_m_data = config.Config_create_model_data(**fit_dict)
        config_sim_cube = config.Config_simulate_cube(**fit_dict)
        kwargs_galmodel = {**config_c_m_data.dict, **config_sim_cube.dict}

        # reload results:
        gal, results = fitting.reload_all_fitting(filename_galmodel=fit_dict['f_model'],
                                    filename_results=fit_dict['f_results'],
                                    fit_method=params['fit_method'])
        # Don't reanalyze anything...
    else:
        raise ValueError(
            '{} not accepted as a fitting method. Please only use "mcmc" or "mpfit"'.format(
                params['fit_method']))

    # Make component plot:
    if fit_dict['do_plotting']:
        plot_bundle_1D(params=params, fit_dict=fit_dict, param_filename=param_filename,
                plot_type=plot_type,overwrite=overwrite,**kwargs_galmodel)


    return None




if __name__ == "__main__":

    param_filename = sys.argv[1]

    try:
        if sys.argv[2].strip().lower() != 'reanalyze':
            datadir = sys.argv[2]
        else:
            datadir = None
    except:
        datadir = None

    try:
        if sys.argv[2].strip().lower() == 'reanalyze':
            reanalyze = True
        else:
            reanalyze = False
    except:
        reanalyze = False

    if reanalyze:
        dysmalpy_reanalyze_single_1D(param_filename=param_filename, datadir=datadir)
    else:
        dysmalpy_fit_single_1D(param_filename=param_filename, datadir=datadir)
