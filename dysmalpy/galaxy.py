# coding=utf8
# Licensed under a 3-clause BSD style license - see LICENSE.rst
#
# Main classes and functions for DYSMALPY for simulating the kinematics of
# a model galaxy and fitting it to observed data.


from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# Standard library
import time
import logging
import copy

# Third party imports
import numpy as np
import astropy.cosmology as apy_cosmo
import astropy.units as u
from astropy.extern import six
import scipy.optimize as scp_opt
import scipy.interpolate as scp_interp


import dill as _pickle

# Local imports
# Package imports
from dysmalpy.instrument import Instrument
from dysmalpy.models import ModelSet, calc_1dprofile
from dysmalpy.data_classes import Data1D, Data2D, Data3D
from dysmalpy.utils import measure_1d_profile_apertures, apply_smoothing_2D

__all__ = ['Galaxy']

# Default cosmology
_default_cosmo = apy_cosmo.FlatLambdaCDM(H0=70., Om0=0.3)

# LOGGER SETTINGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('DysmalPy')

# Function to rebin a cube in the spatial dimension
def rebin(arr, new_2dshape):
    shape = (arr.shape[0],
             new_2dshape[0], arr.shape[1] // new_2dshape[0],
             new_2dshape[1], arr.shape[2] // new_2dshape[1])
    return arr.reshape(shape).sum(-1).sum(-2)


class Galaxy:
    """
    The main object for simulating the kinematics of a galaxy based on
    user provided mass components.
    """

    def __init__(self, z=0, cosmo=_default_cosmo, model=None, instrument=None,
                 data=None, name='galaxy', 
                 data1d=None, data2d=None, data3d=None):

        self._z = z
        self.name = name
        if model is None:
            self.model = ModelSet()
        else:
            self.model = model
        self.data = data
        
        self.data1d = data1d
        self.data2d = data2d
        self.data3d = data3d
        
        self.instrument = instrument
        self._cosmo = cosmo
        self.dscale = self._cosmo.arcsec_per_kpc_proper(self._z).value
        self.model_data = None
        self.model_cube = None

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, value):
        if value < 0:
            raise ValueError("Redshift can't be negative!")
        self._z = value

    @property
    def cosmo(self):
        return self._cosmo

    @cosmo.setter
    def cosmo(self, new_cosmo):
        if isinstance(apy_cosmo.FLRW, new_cosmo):
            raise TypeError("Cosmology must be an astropy.cosmology.FLRW "
                            "instance.")
        if new_cosmo is None:
            self._cosmo = _default_cosmo
        self._cosmo = new_cosmo

    def create_model_data(self, ndim_final=3, nx_sky=None, ny_sky=None,
                          rstep=None, spec_type='velocity', spec_step=10.,
                          spec_start=-1000., nspec=201, line_center=None,
                          spec_unit=(u.km/u.s), aper_centers=None, aper_dist=None,
                          slit_width=None, slit_pa=None, profile1d_type='circ_ap_cube',
                          from_instrument=True, from_data=True,
                          oversample=1, oversize=1, debug=False):

        """
        Simulate an IFU cube then optionally collapse it down to a 2D
        velocity/dispersion field or 1D velocity/dispersion profile.
        
        Convention:
            slit_pa is angle of slit to left side of major axis (eg, neg r is E)
        """

        # Pull parameters from the observed data if specified
        if from_data:

            ndim_final = self.data.ndim

            if ndim_final == 3:

                nx_sky = self.data.shape[2]
                ny_sky = self.data.shape[1]
                nspec = self.data.shape[0]
                spec_ctype = self.data.data.wcs.wcs.ctype[-1]
                if spec_ctype == 'WAVE':
                    spec_type = 'wavelength'
                elif spec_ctype == 'VOPT':
                    spec_type = 'velocity'
                spec_start = self.data.data.spectral_axis[0].value
                spec_unit = self.data.data.spectral_axis.unit
                spec_step = (self.data.data.spectral_axis[1].value -
                             self.data.data.spectral_axis[0].value)
                rstep = self.data.data.wcs.wcs.cdelt[0]*3600.

            elif ndim_final == 2:

                nx_sky = self.data.data['velocity'].shape[1]
                ny_sky = self.data.data['velocity'].shape[0]
                rstep = self.data.pixscale
                if from_instrument:
                    spec_type = self.instrument.spec_type
                    spec_start = self.instrument.spec_start.value
                    spec_step = self.instrument.spec_step.value
                    spec_unit = self.instrument.spec_start.unit
                    nspec = self.instrument.nspec

            elif ndim_final == 1:

                if from_instrument:
                    nx_sky = self.instrument.fov[0]
                    ny_sky = self.instrument.fov[1]
                    spec_type = self.instrument.spec_type
                    spec_start = self.instrument.spec_start.value
                    spec_step = self.instrument.spec_step.value
                    spec_unit = self.instrument.spec_start.unit
                    nspec = self.instrument.nspec
                    rstep = self.instrument.pixscale.value
                else:

                    maxr = 1.5*np.max(np.abs(self.data.rarr))
                    if rstep is None:
                        rstep = np.mean(self.data.rarr[1:] -
                                        self.data.rarr[0:-1])/3.
                    if nx_sky is None:
                        nx_sky = int(np.ceil(maxr/rstep))
                    if ny_sky is None:
                        ny_sky = int(np.ceil(maxr/rstep))

                slit_width = self.data.slit_width
                slit_pa = self.data.slit_pa
                aper_centers = self.data.rarr

        # Pull parameters from the instrument
        elif from_instrument:

            nx_sky = self.instrument.fov[0]
            ny_sky = self.instrument.fov[1]
            spec_type = self.instrument.spec_type
            spec_start = self.instrument.spec_start.value
            spec_step = self.instrument.spec_step.value
            spec_unit = self.instrument.spec_start.unit
            nspec = self.instrument.nspec
            rstep = self.instrument.pixscale.value
            
            try:
                slit_width = self.instrument.slit_width
            except:
                pass
            
        else:

            if (nx_sky is None) | (ny_sky is None) | (rstep is None):

                raise ValueError("At minimum, nx_sky, ny_sky, and rstep must "
                                 "be set if from_instrument and/or from_data"
                                 " is False.")
                                 
        sim_cube, spec = self.model.simulate_cube(nx_sky=nx_sky,
                                                  ny_sky=ny_sky,
                                                  dscale=self.dscale,
                                                  rstep=rstep,
                                                  spec_type=spec_type,
                                                  spec_step=spec_step,
                                                  nspec=nspec,
                                                  spec_start=spec_start,
                                                  spec_unit=spec_unit,
                                                  line_center=line_center,
                                                  oversample=oversample,
                                                  oversize=oversize)
                                                  
        # Correct for any oversampling
        if oversample > 1:
            sim_cube_nooversamp = rebin(sim_cube, (ny_sky*oversize, nx_sky*oversize))
        else:
            sim_cube_nooversamp = sim_cube

        #if debug:
        #self.model_cube_no_convolve = sim_cube_nooversamp

        # Apply beam smearing and/or instrumental spreading
        if self.instrument is not None:
            sim_cube_obs = self.instrument.convolve(cube=sim_cube_nooversamp,
                                                    spec_center=line_center)
        else:
            sim_cube_obs = sim_cube_nooversamp

        # Re-size the cube back down
        if oversize > 1:
            nx_oversize = sim_cube_obs.shape[2]
            ny_oversize = sim_cube_obs.shape[1]
            sim_cube_final = sim_cube_obs[:,
                np.int(ny_oversize/2 - ny_sky/2):np.int(ny_oversize/2+ny_sky/2),
                np.int(nx_oversize/2 - nx_sky/2):np.int(nx_oversize/2+nx_sky/2)]

        else:
            sim_cube_final = sim_cube_obs

            
        self.model_cube = Data3D(cube=sim_cube_final, pixscale=rstep,
                                 spec_type=spec_type, spec_arr=spec,
                                 spec_unit=spec_unit)

        if ndim_final == 3:
            # sim_cube_flat = np.sum(sim_cube_obs*self.data.mask, axis=0)
            # data_cube_flat = np.sum(self.data.data.unmasked_data[:].value*self.data.mask, axis=0)
            # errsq_cube_flat = np.sum( ( self.data.error.unmasked_data[:].value**2 )*self.data.mask, axis=0)
            #
            # # Fill errsq_cube_flat == 0 of *masked* parts with 99.,
            # #   so that later (data*sim/errsq) * mask is finite (and contributes nothing)
            # # Potentially make this a *permanent mask* that can be accessed for faster calculations?
            # mask_flat = np.sum(self.data.mask, axis=0)/self.data.mask.shape[0]
            # mask_flat[mask_flat != 0] = 1.
            # errsq_cube_flat[((errsq_cube_flat == 0.) & (mask_flat==0))] = 99.
            #
            # if self.model.per_spaxel_norm_3D:
            # Do normalization on a per-spaxel basis -- eg, don't care about preserving
            #   M/L ratio information from model.
            # collapse in spectral dimension only: axis 0
            num = np.sum(self.data.mask*(self.data.data.unmasked_data[:].value*
                             sim_cube_obs/(self.data.error.unmasked_data[:].value**2)), axis=0)
            den = np.sum(self.data.mask*
                            (sim_cube_obs**2/(self.data.error.unmasked_data[:].value**2)), axis=0)
            scale = np.abs(num/den)
            scale3D = np.zeros(shape=(1, scale.shape[0], scale.shape[1],))
            scale3D[0, :, :] = scale
            sim_cube_obs *= scale3D
            # else:
            #     scale = np.sum( mask_flat*(data_cube_flat*sim_cube_flat / errsq_cube_flat) )/\
            #                 np.sum( mask_flat*(sim_cube_flat**2 / errsq_cube_flat) )
            #     sim_cube_obs *= scale
            
            # Throw a non-implemented error if smoothing + 3D model:
            if self.data.smoothing_type is not None:
                raise NotImplementedError('Smoothing for 3D output not implemented yet!')
            
            self.model_data = Data3D(cube=sim_cube_obs, pixscale=rstep,
                                     spec_type=spec_type, spec_arr=spec,
                                     spec_unit=spec_unit)

        elif ndim_final == 2:

            if spec_type == "velocity":

                vel = self.model_cube.data.moment1().to(u.km/u.s).value
                disp = self.model_cube.data.linewidth_sigma().to(u.km/u.s).value

            elif spec_type == "wavelength":

                cube_with_vel = self.model_cube.data.with_spectral_unit(
                    u.km/u.s, velocity_convention='optical',
                    rest_value=line_center)

                vel = cube_with_vel.moment1().value
                disp = cube_with_vel.linewidth_sigma().value
                disp[np.isnan(disp)] = 0.

            else:
                raise ValueError("spec_type can only be 'velocity' or "
                                 "'wavelength.'")

            if from_data:
                if self.data.smoothing_type is not None:
                    vel, disp = apply_smoothing_2D(vel, disp,
                                smoothing_type=self.data.smoothing_type,
                                smoothing_npix=self.data.smoothing_npix)
            
            self.model_data = Data2D(pixscale=rstep, velocity=vel,
                                     vel_disp=disp)

        elif ndim_final == 1:

            if spec_type == 'wavelength':

                cube_with_vel = self.model_cube.data.with_spectral_unit(
                    u.km / u.s, velocity_convention='optical',
                    rest_value=line_center)

                cube_data = cube_with_vel.unmasked_data[:]
                vel_arr = cube_with_vel.spectral_axis.to(u.km/u.s).value

            elif spec_type == 'velocity':

                cube_data = sim_cube_obs
                vel_arr = spec

            else:
                raise ValueError("spec_type can only be 'velocity' or "
                                 "'wavelength.'")

            if profile1d_type == 'circ_ap_pv':

                r1d, vel1d, disp1d = calc_1dprofile(cube_data, slit_width,
                                                    slit_pa, rstep, vel_arr)
                vinterp = scp_interp.interp1d(r1d, vel1d,
                                              fill_value='extrapolate')
                disp_interp = scp_interp.interp1d(r1d, disp1d,
                                                  fill_value='extrapolate')
                vel1d = vinterp(aper_centers)
                disp1d = disp_interp(aper_centers)

            elif profile1d_type == 'circ_ap_cube':

                rpix = slit_width/rstep/2.

                if aper_dist is None:
                    aper_dist_pix = 2*rpix
                else:
                    aper_dist_pix = aper_dist/rstep

                aper_centers_pix = aper_centers/rstep
                aper_centers_pixout, flux1d, vel1d, disp1d = measure_1d_profile_apertures(cube_data, rpix, slit_pa,
                                                                          vel_arr,
                                                                          dr=aper_dist_pix,
                                                                          ap_centers=aper_centers_pix,
                                                                          debug=debug)
                aper_centers = aper_centers_pixout*rstep
                                                                          

            else:
                raise TypeError('Unknown method for measuring the 1D profiles.')


            self.model_data = Data1D(r=aper_centers, velocity=vel1d,
                                     vel_disp=disp1d, slit_width=slit_width,
                                     slit_pa=slit_pa)

    #
    def preserve_self(self, filename=None):
        # def save_galaxy_model(self, galaxy=None, filename=None):
        if filename is not None:
            galtmp = copy.deepcopy(self)
            
            galtmp.filename_velocity = copy.deepcopy(galtmp.data.filename_velocity)
            galtmp.filename_dispersion = copy.deepcopy(galtmp.data.filename_dispersion)
            
            galtmp.data = None
            galtmp.model_data = None
            galtmp.model_cube = None
            
            # galtmp.instrument = copy.deepcopy(galaxy.instrument)
            # galtmp.model = modtmp
            
            #dump_pickle(galtmp, filename=filename) # Save mcmcResults class
            _pickle.dump(galtmp, open(filename, "wb") )
            
            return None
            
    def load_self(self, filename=None):
        if filename is not None:
            galtmp = _pickle.load(open(filename, "rb"))
            # Reset
            #self = copy.deepcopy(galtmp)
            #return self
            return galtmp
            
            
def load_galaxy_object(filename=None):
    gal = Galaxy()
    gal = gal.load_self(filename=filename)
    return gal
    