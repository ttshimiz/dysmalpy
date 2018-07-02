# coding=utf8
# Licensed under a 3-clause BSD style license - see LICENSE.rst
#
# Functions for plotting DYSMALPY kinematic model fit results


from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# Standard library
import logging
import copy

# Third party imports
import numpy as np
from astropy.extern import six
import astropy.units as u
import matplotlib
matplotlib.use('agg')

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
from mpl_toolkits.axes_grid1 import ImageGrid, AxesGrid

import corner

__all__ = ['plot_trace', 'plot_corner', 'plot_bestfit']


# LOGGER SETTINGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('DysmalPy')


def plot_trace(mcmcResults, fileout=None):
    """
    Plot trace of MCMC walkers
    """
    names = make_clean_mcmc_plot_names(mcmcResults)

    ######################################
    # Setup plot:
    f = plt.figure()
    scale = 1.75
    nRows = len(names)
    nWalkers = mcmcResults.sampler['nWalkers']
    
    f.set_size_inches(4.*scale, nRows*scale)
    gs = gridspec.GridSpec(nRows, 1, hspace=0.2)

    axes = []
    alpha = max(0.01, 1./nWalkers)
    
    # Define random color inds for tracking some walkers:
    nTraceWalkers = 5
    cmap = cm.viridis
    alphaTrace = 0.8
    lwTrace = 1.5
    trace_inds = np.random.randint(0,nWalkers, size=nTraceWalkers)
    trace_colors = []
    for i in six.moves.xrange(nTraceWalkers):
        trace_colors.append(cmap(1./np.float(nTraceWalkers)*i))
    
    norm_inds = np.setdiff1d(range(nWalkers), trace_inds)
    

    for k in six.moves.xrange(nRows):
        axes.append(plt.subplot(gs[k,0]))
        
        axes[k].plot(mcmcResults.sampler['chain'][norm_inds,:,k].T, '-', color='black', alpha=alpha)
        
        for j in six.moves.xrange(nTraceWalkers):
            axes[k].plot(mcmcResults.sampler['chain'][trace_inds[j],:,k].T, '-', 
                    color=trace_colors[j], lw=lwTrace, alpha=alphaTrace)
            
            
        axes[k].set_ylabel(names[k])

        if k == nRows-1:
            axes[k].set_xlabel('Step number')
        else:
            axes[k].set_xticks([])

    #############################################################
    # Save to file:
    if fileout is not None:
        plt.savefig(fileout, bbox_inches='tight', dpi=300)
        plt.close()
    else:
        plt.show()


    return None


def plot_corner(mcmcResults, fileout=None, step_slice=None):
    """
    Plot corner plot of MCMC result posterior distributions.
    Optional:
            step slice: 2 element tuple/array with beginning and end step number to use
    """
    names = make_clean_mcmc_plot_names(mcmcResults)
    
    if step_slice is None:
        sampler_chain = mcmcResults.sampler['flatchain']
    else:
        sampler_chain = mcmcResults.sampler['chain'][:,step_slice[0]:step_slice[1],:].reshape((-1, mcmcResults.sampler['nParam']))

    title_kwargs = {'horizontalalignment': 'left', 'x': 0.}
    fig = corner.corner(sampler_chain,
                            labels=names,
                            quantiles= [.02275, 0.15865, 0.84135, .97725],
                            truths=mcmcResults.bestfit_parameters,
                            plot_datapoints=False,
                            show_titles=True,
                            bins=40,
                            plot_contours=True,
                            verbose=False,
                            title_kwargs=title_kwargs)
                            
    axes = fig.axes
    nFreeParam = len(mcmcResults.bestfit_parameters)
    for i in six.moves.xrange(nFreeParam):
        ax = axes[i*nFreeParam + i]
        # Format the quantile display.
        best = mcmcResults.bestfit_parameters[i]
        q_m = mcmcResults.bestfit_parameters_l68_err[i]
        q_p = mcmcResults.bestfit_parameters_u68_err[i]
        title_fmt=".2f"
        fmt = "{{0:{0}}}".format(title_fmt).format
        title = r"${{{0}}}_{{-{1}}}^{{+{2}}}$"
        title = title.format(fmt(best), fmt(q_m), fmt(q_p))
        
        # Add in the column name if it's given.
        if names is not None:
            title = "{0} = {1}".format(names[i], title)
        ax.set_title(title, **title_kwargs)

    if fileout is not None:
        plt.savefig(fileout, bbox_inches='tight')#, dpi=300)
        plt.close(fig)
    else:
        plt.show()

    return None
    
def plot_data_model_comparison_1D(gal, 
            data = None,
            theta = None, 
            oversample=1,
            oversize=1,
            fitdispersion=True, 
            fileout=None):
    ######################################
    # Setup data/model comparison: if this isn't the fit dimension 
    #   data/model comparison (eg, fit in 2D, showing 1D comparison)
    if data is not None:

        # Setup the model with the correct dimensionality:
        galnew = copy.deepcopy(gal)
        galnew.data = data
        galnew.create_model_data(oversample=oversample, oversize=oversize,
                              line_center=galnew.model.line_center)
        model_data = galnew.model_data

    else:
        # Default: fit in 1D, compare to 1D data:
        data = gal.data
        model_data = gal.model_data
    
    # Correct model for instrument dispersion if the data is instrument corrected:
    if 'inst_corr' in data.data.keys():
        if (data.data['inst_corr']):
            model_data.data['dispersion'] = \
                np.sqrt( model_data.data['dispersion']**2 - \
                    gal.instrument.lsf.dispersion.to(u.km/u.s).value**2 )
    
    
    ######################################
    # Setup plot:
    f = plt.figure()
    scale = 3.5
    if fitdispersion:
        ncols = 2
    else:
        ncols = 1
    nrows = 2
    f.set_size_inches(1.1*ncols*scale, nrows*scale)
    gs = gridspec.GridSpec(nrows, ncols, wspace=0.35, hspace=0.2)

    keyxtitle = r'$r$ [arcsec]'
    keyyarr = ['velocity', 'dispersion']
    keyytitlearr = [r'$V$ [km/s]', r'$\sigma$ [km/s]']
    keyyresidtitlearr = [r'$V_{\mathrm{model}} - V_{\mathrm{data}}$ [km/s]',
                    r'$\sigma_{\mathrm{model}} - \sigma_{\mathrm{data}}$ [km/s]']

    errbar_lw = 0.5
    errbar_cap = 1.5

    axes = []
    k = -1
    for j in six.moves.xrange(ncols):
        # Comparison:
        axes.append(plt.subplot(gs[0,j]))
        k += 1
        axes[k].errorbar( data.rarr, data.data[keyyarr[j]],
                xerr=None, yerr = data.error[keyyarr[j]],
                marker=None, ls='None', ecolor='k', zorder=-1.,
                lw = errbar_lw,capthick= errbar_lw,capsize=errbar_cap,label=None )
        axes[k].scatter( data.rarr, data.data[keyyarr[j]],
            c='black', marker='o', s=25, lw=1, label=None)
            
            
        axes[k].scatter( data.rarr, model_data.data[keyyarr[j]],
            c='red', marker='s', s=25, lw=1, label=None)
        axes[k].set_xlabel(keyxtitle)
        axes[k].set_ylabel(keyytitlearr[j])
        axes[k].axhline(y=0, ls='--', color='k', zorder=-10.)
        # Residuals:
        axes.append(plt.subplot(gs[1,j]))
        k += 1
        axes[k].errorbar( data.rarr, model_data.data[keyyarr[j]]-data.data[keyyarr[j]],
                xerr=None, yerr = data.error[keyyarr[j]],
                marker=None, ls='None', ecolor='k', zorder=-1.,
                lw = errbar_lw,capthick= errbar_lw,capsize=errbar_cap,label=None )
        axes[k].scatter( data.rarr, model_data.data[keyyarr[j]]-data.data[keyyarr[j]],
            c='red', marker='s', s=25, lw=1, label=None)
        axes[k].axhline(y=0, ls='--', color='k', zorder=-10.)
        axes[k].set_xlabel(keyxtitle)
        axes[k].set_ylabel(keyyresidtitlearr[j])
    #############################################################
    # Save to file:
    if fileout is not None:
        plt.savefig(fileout, bbox_inches='tight', dpi=300)
        plt.close()
    else:
        plt.show()
    

def plot_data_model_comparison_2D(gal, 
            theta = None, 
            oversample=1,
            oversize=1,
            fitdispersion=True, 
            fileout=None):
    #
    ######################################
    # Setup plot:
    f = plt.figure(figsize=(9.5, 6))
    scale = 3.5
    if fitdispersion:
        grid_vel = ImageGrid(f, 211,
                             nrows_ncols=(1, 3),
                             direction="row",
                             axes_pad=0.5,
                             add_all=True,
                             label_mode="1",
                             share_all=True,
                             cbar_location="right",
                             cbar_mode="each",
                             cbar_size="5%",
                             cbar_pad="1%",
                             )

        grid_disp = ImageGrid(f, 212,
                              nrows_ncols=(1, 3),
                              direction="row",
                              axes_pad=0.5,
                              add_all=True,
                              label_mode="1",
                              share_all=True,
                              cbar_location="right",
                              cbar_mode="each",
                              cbar_size="5%",
                              cbar_pad="1%",
                              )

    else:
        grid_vel = ImageGrid(f, 111,
                             nrows_ncols=(1, 3),
                             direction="row",
                             axes_pad=0.5,
                             add_all=True,
                             label_mode="1",
                             share_all=True,
                             cbar_location="right",
                             cbar_mode="each",
                             cbar_size="5%",
                             cbar_pad="1%",
                             )

    #f.set_size_inches(1.1*ncols*scale, nrows*scale)
    #gs = gridspec.GridSpec(nrows, ncols, wspace=0.05, hspace=0.05)

    keyxarr = ['data', 'model', 'residual']
    keyyarr = ['velocity', 'dispersion']
    keyxtitlearr = ['Data', 'Model', 'Residual']
    keyytitlearr = [r'$V$', r'$\sigma$']

    int_mode = "nearest"
    origin = 'lower'
    cmap =  cm.nipy_spectral
    cmap.set_bad(color='k')

    vel_vmin = gal.data.data['velocity'][gal.data.mask].min()
    vel_vmax = gal.data.data['velocity'][gal.data.mask].max()

    for ax, k, xt in zip(grid_vel, keyxarr, keyxtitlearr):
        if k == 'data':
            im = gal.data.data['velocity'].copy()
            im[~gal.data.mask] = np.nan
        elif k == 'model':
            im = gal.model_data.data['velocity'].copy()
            im[~gal.data.mask] = np.nan
        elif k == 'residual':
            im = gal.data.data['velocity'] - gal.model_data.data['velocity']
            im[~gal.data.mask] = np.nan
        else:
            raise ValueError("key not supported.")

        imax = ax.imshow(im, cmap=cmap, interpolation=int_mode,
                         vmin=vel_vmin, vmax=vel_vmax, origin=origin)

        if k == 'data':
            ax.set_ylabel(keyytitlearr[0])
            ax.tick_params(which='both', top='off', bottom='off',
                           left='off', right='off', labelbottom='off',
                           labelleft='off')
            for sp in ax.spines.values():
                sp.set_visible(False)
        else:
            ax.set_axis_off()

        ax.set_title(xt)

        cbar = ax.cax.colorbar(imax)
        cbar.ax.tick_params(labelsize=8)

    if fitdispersion:

        disp_vmin = gal.data.data['dispersion'][gal.data.mask].min()
        disp_vmax = gal.data.data['dispersion'][gal.data.mask].max()

        for ax, k in zip(grid_disp, keyxarr):
            if k == 'data':
                im = gal.data.data['dispersion'].copy()
                im[~gal.data.mask] = np.nan
            elif k == 'model':
                im = gal.model_data.data['dispersion'].copy()
                im[~gal.data.mask] = np.nan

                # Correct model for instrument dispersion
                # if the data is instrument corrected:
                if 'inst_corr' in gal.data.data.keys():
                    if (gal.data.data['inst_corr']):
                        im = np.sqrt(im ** 2 - gal.instrument.lsf.dispersion.to(
                                     u.km / u.s).value ** 2)

            elif k == 'residual':

                im_model = gal.model_data.data['dispersion'].copy()
                if 'inst_corr' in gal.data.data.keys():
                    if (gal.data.data['inst_corr']):
                        im_model = np.sqrt(im_model ** 2 -
                                           gal.instrument.lsf.dispersion.to(
                                           u.km / u.s).value ** 2)


                im = gal.data.data['dispersion'] - im_model
                im[~gal.data.mask] = np.nan

            else:
                raise ValueError("key not supported.")

            if k != 'residual':
                imax = ax.imshow(im, cmap=cmap, interpolation=int_mode,
                                 vmin=disp_vmin, vmax=disp_vmax, origin=origin)
            else:
                imax = ax.imshow(im, cmap=cmap, interpolation=int_mode,
                                 origin=origin)

            if k == 'data':
                ax.set_ylabel(keyytitlearr[1])
                ax.tick_params(which='both', top='off', bottom='off',
                               left='off', right='off', labelbottom='off',
                               labelleft='off')
                for sp in ax.spines.values():
                    sp.set_visible(False)
            else:
                ax.set_axis_off()

            cbar = ax.cax.colorbar(imax)
            cbar.ax.tick_params(labelsize=8)

    #############################################################
    # Save to file:
    if fileout is not None:
        plt.savefig(fileout, bbox_inches='tight', dpi=300)
        plt.close()
    else:
        plt.draw()
        plt.show()
        
        
def plot_model_multid(gal, 
            theta=None, 
            oversample=1, 
            oversize=1, 
            fileout=None):
        
    #
    ######################################
    # Setup plot:
    f = plt.figure(figsize=(6., 6))
    scale = 3.5
    ncols = 2
    
    grid_1D = [plt.subplot2grid((2, 2), (0, 0)), plt.subplot2grid((2, 2), (0, 1))]
    
    # gs_outer= plt.subplot(211)
    # 
    # 
    # gs = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs_outer[0])
    # 
    # axes = []
    # k = -1
    # grid_1D = []
    # for j in six.moves.xrange(ncols):
    #     # Comparison:
    #     grid_1D.append(plt.subplot(gs[0,j]))
    #     
    # #grid_1D = [plt.subplot2grid((2, 2), (2, 0)), ax5 = plt.subplot2grid((3, 3), (2, 1))
    #     
        
    # grid_1D = ImageGrid(f, 211,
    #                      nrows_ncols=(1, ncols),
    #                      direction="row",
    #                      axes_pad=0.5,
    #                      add_all=True,
    #                      label_mode="1",
    #                      share_all=True,
    #                      cbar_mode="None"
    #                      )
    
    # grid_1D = AxesGrid(f, 211, 
    #                  nrows_ncols=(1, ncols),
    #                  direction="row",
    #                  axes_pad=0.5,
    #                  add_all=True,
    #                  share_all=False, 
    #                  label_mode="1",
    #                  )

    grid_2D = ImageGrid(f, 212,
                          nrows_ncols=(1, ncols),
                          direction="row",
                          axes_pad=0.5,
                          add_all=True,
                          label_mode="1",
                          share_all=True,
                          cbar_location="right",
                          cbar_mode="each",
                          cbar_size="5%",
                          cbar_pad="1%",
                          )
    
    
    
    
    if theta is not None:
        gal.model.update_parameters(theta)     # Update the parameters
        
    try:
        gal.create_model_data(oversample=oversample, oversize=oversize,
                              line_center=gal.model.line_center, ndim_final=1)
    except:
        gal.create_model_data(oversample=oversample, oversize=oversize,
                              line_center=gal.model.line_center, ndim_final=1, from_data=False)
    galnew = copy.deepcopy(gal)
    model_data = galnew.model_data
    data = galnew.data
    if 'inst_corr' in data.data.keys():
        if (data.data['inst_corr']):
            model_data.data['dispersion'] = \
                np.sqrt( model_data.data['dispersion']**2 - \
                    gal.instrument.lsf.dispersion.to(u.km/u.s).value**2 )
                    
                    


    ######################################

    keyxtitle = r'$r$ [arcsec]'
    keyyarr = ['velocity', 'dispersion']
    keyytitlearr = [r'$V$ [km/s]', r'$\sigma$ [km/s]']

    errbar_lw = 0.5
    errbar_cap = 1.5

    k = -1
    for j in six.moves.xrange(ncols):
        # Comparison:
        k += 1
        ax = grid_1D[k]
        
        try:
            ax.scatter( data.rarr, data.data[keyyarr[j]],
                c='black', marker='o', s=25, lw=1, label=None)
        except:
            pass
        
        ax.scatter( model_data.rarr, model_data.data[keyyarr[j]],
            c='red', marker='s', s=25, lw=1, label=None)
        ax.set_xlabel(keyxtitle)
        ax.set_ylabel(keyytitlearr[j])
        ax.axhline(y=0, ls='--', color='k', zorder=-10.)
        
        
    ######################################
    
    gal.create_model_data(oversample=oversample, oversize=oversize,
                              line_center=gal.model.line_center, ndim_final=2, 
                              from_data=False)


    keyxarr = ['model']
    keyyarr = ['velocity', 'dispersion']
    keyxtitlearr = ['Model']
    keyytitlearr = [r'$V$', r'$\sigma$']

    int_mode = "nearest"
    origin = 'lower'
    cmap =  cm.nipy_spectral
    cmap.set_bad(color='k')
    
    
    
    for ax, k, xt in zip(grid_2D, keyyarr, keyytitlearr):
        if k == 'velocity':
            im = gal.model_data.data['velocity'].copy()
            #im[~gal.data.mask] = np.nan
            im[~np.isfinite(im)] = 0.
            
            vmin = im.min()
            vmax = im.max()
            
            if max(np.abs(vmin), np.abs(vmax)) > 1000.:
                vmin = -300.
                vmax = 300.
            
        elif k == 'dispersion':
            im = gal.model_data.data['dispersion'].copy()
            #im[~gal.data.mask] = np.nan
            
            
            # Correct model for instrument dispersion
            # if the data is instrument corrected:
            if 'inst_corr' in gal.data.data.keys():
                if (gal.data.data['inst_corr']):
                    im = np.sqrt(im ** 2 - gal.instrument.lsf.dispersion.to(
                                 u.km / u.s).value ** 2)
            im[~np.isfinite(im)] = 0.
            
            vmin = im.min()
            vmax = im.max()
            
            if max(np.abs(vmin), np.abs(vmax)) > 500.:
                vmin = 0.
                vmax = 200.
            
        else:
            raise ValueError("key not supported.")
        
        
        imax = ax.imshow(im, cmap=cmap, interpolation=int_mode,
                         vmin=vmin, vmax=vmax, origin=origin)

        ax.set_ylabel(keyytitlearr[0])
        ax.tick_params(which='both', top='off', bottom='off',
                       left='off', right='off', labelbottom='off',
                       labelleft='off')
        for sp in ax.spines.values():
            sp.set_visible(False)
        # else:
        #     ax.set_axis_off()

        #ax.set_title(xt)

        cbar = ax.cax.colorbar(imax)
        cbar.ax.tick_params(labelsize=8)


    #############################################################
    # Save to file:
    if fileout is not None:
        plt.savefig(fileout, bbox_inches='tight', dpi=300)
        plt.close()
    else:
        plt.draw()
        plt.show()
    
    return None
    
    
        
def plot_data_model_comparison(gal, 
            theta = None, 
            oversample=1,
            oversize=1,
            fitdispersion=True, 
            fileout=None):
    """
    Plot data, model, and residuals between the data and this model.
    """
    if theta is not None:
        gal.model.update_parameters(theta)     # Update the parameters
        gal.create_model_data(oversample=oversample, oversize=oversize,
                              line_center=gal.model.line_center)

    if gal.data.ndim == 1:
        plot_data_model_comparison_1D(gal, 
                    data = None,
                    theta = theta, 
                    oversample=oversample,
                    oversize=oversize,
                    fitdispersion=fitdispersion, 
                    fileout=fileout)
    elif gal.data.ndim == 2:
        plot_data_model_comparison_2D(gal, 
                    theta = theta, 
                    oversample=oversample,
                    oversize=oversize,
                    fitdispersion=fitdispersion, 
                    fileout=fileout)
    elif gal.data.ndim == 3:
        logger.warning("Need to implement fitting plot_bestfit for 3D *AFTER* Dysmalpy datastructure finalized!")
    else:
        logger.warning("nDim="+str(gal.data.ndim)+" not supported!")
        raise ValueError
    
    return None

def plot_bestfit(mcmcResults, gal,
            oversample=1,
            oversize=1,
            fitdispersion=True,
            fileout=None):
    """
    Plot data, bestfit model, and residuals from the MCMC fitting.
    """
    plot_data_model_comparison(gal, theta = mcmcResults.bestfit_parameters, 
            oversample=oversample, oversize=oversize, fitdispersion=fitdispersion, fileout=fileout)
                
    return None


def make_clean_mcmc_plot_names(mcmcResults):
    names = []
    for key in mcmcResults.free_param_names.keys():
        for i in six.moves.xrange(len(mcmcResults.free_param_names[key])):
            param = mcmcResults.free_param_names[key][i]
            key_nice = " ".join(key.split("_"))
            param_nice = " ".join(param.split("_"))
            names.append(key_nice+': '+param_nice)

    return names


