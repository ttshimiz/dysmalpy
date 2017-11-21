# coding=utf8
# Licensed under a 3-clause BSD style license - see LICENSE.rst
#
# File containing all of the available models to use build the
# galaxy

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# Standard library
import os
import abc
import logging
from collections import OrderedDict

# Third party imports
import numpy as np
import scipy.special as scp_spec
import scipy.io as scp_io
import scipy.interpolate as scp_interp
import scipy.optimize as scp_opt
import scipy.ndimage as scp_ndi
import astropy.constants as apy_con
import astropy.units as u
from astropy.modeling import Model
import astropy.cosmology as apy_cosmo

# Local imports
from dysmalpy.parameters import DysmalParameter

__all__ = ['ModelSet', 'MassModel', 'Sersic', 'NFW', 'HaloMo98',
           'DispersionConst', 'Geometry']

# NOORDERMEER DIRECTORY
path = os.path.abspath(__file__)
dir_path = os.path.dirname(path)
_dir_noordermeer = dir_path+"/data/noordermeer/"

# CONSTANTS
G = apy_con.G
Msun = apy_con.M_sun
pc = apy_con.pc

# DEFAULT COSMOLOGY
_default_cosmo = apy_cosmo.FlatLambdaCDM(H0=70., Om0=0.3)

# LOGGER SETTINGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('DysmalPy')

# TODO: Tied parameters are NOT automatically updated when variables change!!
# TODO: Need to keep track during the fitting!


def sersic_mr(r, mass, n, r_eff):
    """Radial mass function for a generic sersic model"""

    bn = scp_spec.gammaincinv(2. * n, 0.5)
    alpha = r_eff / (bn ** n)
    amp = (mass / (2 * np.pi) / alpha ** 2 / n /
           scp_spec.gamma(2. * n))
    mr = amp * np.exp(-bn * (r / r_eff) ** (1. / n))

    return mr


def sersic_menc(r, mass, n, r_eff):
    """Enclosed mass as a function of r for a sersic model"""

    bn = scp_spec.gammaincinv(2. * n, 0.5)
    integ = scp_spec.gammainc(2 * n, bn * (r / r_eff) ** (1. / n))
    norm = mass

    return norm*integ


def apply_noord_flat(r, r_eff, mass, n, invq):

    noordermeer_n = np.arange(0.5, 8.1, 0.1)  # Sersic indices
    noordermeer_invq = np.array([1, 2, 3, 4, 5, 6, 8, 10, 20,
                                 100])  # 1:1, 1:2, 1:3, ...flattening

    nearest_n = noordermeer_n[
        np.argmin(np.abs(noordermeer_n - n))]
    nearest_q = noordermeer_invq[
        np.argmin(np.abs(noordermeer_invq - invq))]

    # Need to do this internally instead of relying on IDL save files!!
    file_noord = _dir_noordermeer + 'VC_n{0:3.1f}_invq{1}.save'.format(
        nearest_n, nearest_q)
    restNVC = scp_io.readsav(file_noord)
    N2008_vcirc = restNVC.N2008_vcirc
    N2008_rad = restNVC.N2008_rad
    N2008_Re = restNVC.N2008_Re
    N2008_mass = restNVC.N2008_mass

    v_interp = scp_interp.interp1d(N2008_rad, N2008_vcirc,
                                   fill_value="extrapolate")
    vcirc = (v_interp(r / r_eff * N2008_Re) * np.sqrt(
             mass / N2008_mass) * np.sqrt(N2008_Re / r_eff))

    return vcirc

def area_segm(rr, dd):

    return (rr**2 * np.arccos(dd/rr) -
            dd * np.sqrt(2. * rr * (rr-dd) - (rr-dd)**2))


def calc_1dprofile(cube, slit_width, slit_angle, pxs, vx, soff=0.):

    # Get the data for the observed velocity profile
    cube_shape = cube.shape
    psize = cube_shape[1]
    vsize = cube_shape[0]
    lin = np.arange(psize) - np.fix(psize/2.)
    veldata = scp_ndi.interpolation.rotate(cube, slit_angle, axes=(2, 1),
                                           reshape=False)
    tmpn = (((lin*pxs) <= (soff+slit_width/2.)) &
            ((lin*pxs) >= (soff-slit_width/2.)))
    data = np.zeros((psize, vsize))
    flux = np.zeros(psize)

    yvec = vx
    xvec = lin*pxs

    for i in range(psize):
        for j in range(vsize):
            data[i, j] = np.mean(veldata[j, i, tmpn])
        tmp = data[i]
        flux[i] = np.sum(tmp)

    flux = flux / np.max(flux) * 10.
    pvec = (flux < 0.)

    # Calculate circular segments
    rr = 0.5 * slit_width
    pp = pxs

    nslice = np.int(1 + 2 * np.ceil((rr - 0.5 * pp) / pp))

    circaper_idx = np.arange(nslice) - 0.5 * (nslice - 1)
    circaper_sc = np.zeros(nslice)

    circaper_sc[int(0.5*nslice - 0.5)] = (np.pi*rr**2 -
                                          2.*area_segm(rr, 0.5*pp))

    if nslice > 1:
        circaper_sc[0] = area_segm(rr, (0.5*nslice - 1)*pp)
        circaper_sc[nslice-1] = circaper_sc[0]

    if nslice > 3:
        for cnt in range(1, int(0.5*(nslice-3))+1):
            circaper_sc[cnt] = (area_segm(rr, (0.5*nslice - 1. - cnt)*pp) -
                                area_segm(rr, (0.5*nslice - cnt)*pp))
            circaper_sc[nslice-1-cnt] = circaper_sc[cnt]

    circaper_vel = np.zeros(psize)
    circaper_disp = np.zeros(psize)

    nidx = len(circaper_idx)
    for i in range(psize):
        tot_vnum = 0.
        tot_denom = 0.
        cnt_idx = 0
        cnt_start = int(i + circaper_idx[0]) if (i + circaper_idx[0]) > 0 else 0
        cnt_end = (int(i + circaper_idx[nidx-1]) if (i + circaper_idx[nidx-1]) <
                                                    (psize-1) else (psize-1))
        for cnt in range(cnt_start, cnt_end+1):
            tmp = data[cnt]
            tot_vnum += circaper_sc[cnt_idx] * np.sum(tmp*yvec)
            tot_denom += circaper_sc[cnt_idx] * np.sum(tmp)
            cnt_idx = cnt_idx + 1

        circaper_vel[i] = tot_vnum / tot_denom

        tot_dnum = 0.
        cnt_idx = 0
        for cnt in range(cnt_start, cnt_end+1):
            tmp = data[cnt]
            tot_dnum = (tot_dnum + circaper_sc[cnt_idx] *
                        np.sum(tmp*(yvec-circaper_vel[i])**2))
            cnt_idx = cnt_idx + 1

        circaper_disp[i] = np.sqrt(tot_dnum / tot_denom)

    if np.sum(pvec) > 0.:
        circaper_vel[pvec] = -1.e3
        circaper_disp[pvec] = 0.

    return xvec, circaper_vel, circaper_disp


# Generic model container which tracks all components, parameters,
# parameter settings, model settings, etc.
class ModelSet:

    def __init__(self):

        self.mass_components = OrderedDict()
        self.components = OrderedDict()
        self.light_components = OrderedDict()
        self.geometry = None
        self.dispersion_profile = None
        self.zprofile = None
        self.parameters = None
        self.fixed = OrderedDict()
        self.tied = OrderedDict()
        self.param_names = OrderedDict()
        self._param_keys = OrderedDict()
        self.nparams = 0
        self.nparams_free = 0
        self.nparams_tied = 0
        self.kinematic_options = KinematicOptions()
        self.line_center = None

    def add_component(self, model, name=None, light=False):
        """Add a model component to the set"""

        # Check to make sure its the correct class
        if isinstance(model, _DysmalModel):

            # Check to make sure it has a name
            if (name is None) & (model.name is None):
                raise ValueError('Please give this component a name!')

            elif name is not None:
                model = model.rename(name)

            if model._type == 'mass':

                # Make sure there isn't a mass component already named this
                if list(self.mass_components.keys()).count(model.name) > 0:
                    raise ValueError('Component already exists. Please give'
                                     'it a unique name.')
                else:
                    self.mass_components[model.name] = True

                # Only mass components can also be a light component
                # TODO: When I add in outflow components I'll need to change this
                if light:
                    self.light_components[model.name] = True
                else:
                    self.light_components[model.name] = False

            elif model._type == 'geometry':
                if self.geometry is not None:
                    logger.warning('Current Geometry model is being '
                                   'overwritten!')
                self.geometry = model
                self.mass_components[model.name] = False

            elif model._type == 'dispersion':
                if self.dispersion_profile is not None:
                    logger.warning('Current Dispersion model is being '
                                   'overwritten!')
                self.dispersion_profile = model
                self.mass_components[model.name] = False

            elif model._type == 'zheight':
                if self.zprofile is not None:
                    logger.warning('Current z-height model is being '
                                   'overwritten!')
                self.zprofile = model
                self.mass_components[model.name] = False

            else:
                raise TypeError("This model type is not known. Must be one of"
                                "'mass', 'geometry', or 'dispersion.'")

            self._add_comp(model)

        else:

            raise TypeError('Model component must be a '
                            'dysmalpy.models.DysmalModel instance!')

    def _add_comp(self, model):

        # Update the components list
        self.components[model.name] = model

        # Update the parameters and parameters_free arrays
        if self.parameters is None:
            self.parameters = model.parameters
        else:

            self.parameters = np.concatenate([self.parameters,
                                              model.parameters])
        self.param_names[model.name] = model.param_names
        self.fixed[model.name] = model.fixed
        self.tied[model.name] = model.tied

        # Update the dictionaries containing the locations of the parameters
        # in the parameters array. Also count number of tied parameters
        key_dict = OrderedDict()
        ntied = 0
        for i, p in enumerate(model.param_names):
            key_dict[p] = i + self.nparams
            if model.tied[p]:
                ntied += 1

        self._param_keys[model.name] = key_dict
        self.nparams += len(model.param_names)
        self.nparams_free += (len(model.param_names) - sum(model.fixed.values())
                              - ntied)
        self.nparams_tied += ntied

    def set_parameter_value(self, model_name, param_name, value):
        """Method to set a specific parameter value"""

        try:
            comp = self.components[model_name]
        except KeyError:
            raise KeyError('Model not part of the set.')

        try:
            param_i = comp.param_names.index(param_name)
        except ValueError:
            raise ValueError('Parameter is not part of model.')

        self.components[model_name].parameters[param_i] = value
        self.parameters[self._param_keys[model_name][param_name]] = value

    def set_parameter_fixed(self, model_name, param_name, fix):
        """Method to set a specific parameter fixed or not"""

        try:
            comp = self.components[model_name]
        except KeyError:
            raise KeyError('Model not part of the set.')

        try:
            param_i = comp.param_names.index(param_name)
        except ValueError:
            raise ValueError('Parameter is not part of model.')

        self.components[model_name].fixed[param_name] = fix
        self.fixed[model_name][param_name] = fix
        if fix:
            self.nparams_free -= 1
        else:
            self.nparams_free += 1

    def update_parameters(self, theta):
        """Update all of the free parameters of the model
           Then update all of the tied parameters.
        """

        # Sanity check to make sure the array given is the right length
        if len(theta) != self.nparams_free:
            raise ValueError('Length of theta is not equal to number '
                             'of free parameters, {}'.format(self.nparams_free))

        # Loop over all of the parameters
        pfree, pfree_keys = self._get_free_parameters()
        for cmp in pfree_keys:
            for pp in pfree_keys[cmp]:
                ind = pfree_keys[cmp][pp]
                if ind != -99:
                    self.set_parameter_value(cmp, pp, theta[ind])

        # Now update all of the tied parameters if there are any
        if self.nparams_tied > 0:
            for cmp in self.tied:
                for pp in self.tied[cmp]:
                    if self.tied[cmp][pp]:
                        new_value = self.tied[cmp][pp](self)
                        self.set_parameter_value(cmp, pp, new_value)

    # Methods to grab the free parameters and keys
    def _get_free_parameters(self):
        p = np.zeros(self.nparams_free)
        pkeys = OrderedDict()
        j = 0
        for cmp in self.fixed:
            pkeys[cmp] = OrderedDict()
            for pm in self.fixed[cmp]:
                if self.fixed[cmp][pm] | np.bool(self.tied[cmp][pm]):
                    pkeys[cmp][pm] = -99
                else:
                    pkeys[cmp][pm] = j
                    p[j] = self.parameters[self._param_keys[cmp][pm]]
                    j += 1
        return p, pkeys

    def get_free_parameters_values(self):
        pfree, pfree_keys = self._get_free_parameters()
        return pfree

    def get_free_parameter_keys(self):
        pfree, pfree_keys = self._get_free_parameters()
        return pfree_keys

    def get_log_prior(self):
        log_prior_model = 0.
        pfree_dict = self.get_free_parameter_keys()
        comps_names = pfree_dict.keys()
        outstr = ""
        outstrp = ""
        outth = ""
        for compn in comps_names:
            comp = self.components.__getitem__(compn)
            params_names = pfree_dict[compn].keys()
            for paramn in params_names:
                if pfree_dict[compn][paramn] >= 0:
                    # Free parameter: add to total prior
                    outth += "{}, ".format(self.parameters[self._param_keys[compn][paramn]])
                    outstrp += "{}-{}, ".format(compn, paramn)
                    outstr += "{}, ".format(comp.prior[paramn].log_prior(comp.__getattribute__(paramn)))
                    log_prior_model += comp.prior[paramn].log_prior(comp.__getattribute__(paramn))
        print("params= {}".format(outstrp))
        print("theta= {}".format(outth))
        print("indiv lprior= {}".format(outstr))
        print("get_free_parameters={}".format(self._get_free_parameters()))
        return log_prior_model

    def velocity_profile(self, r):
        """
        Method to calculate the 1D velocity profile
        as a function of radius
        """

        # First check to make sure there is at least one mass component in the
        # model set.
        if len(self.mass_components) == 0:
            raise AttributeError("There are no mass components so a velocity "
                                 "can't be calculated.")
        else:

            vdm = np.zeros(len(r))
            vbaryon = np.zeros(len(r))

            for cmp in self.mass_components:

                if self.mass_components[cmp]:
                    mcomp = self.components[cmp]
                    cmpnt_v = mcomp.circular_velocity(r)
                    if mcomp._subtype == 'dark_matter':

                        vdm = np.sqrt(vdm ** 2 + cmpnt_v ** 2)

                    elif mcomp._subtype == 'baryonic':

                        vbaryon = np.sqrt(vbaryon ** 2 + cmpnt_v ** 2)

                    else:
                        raise TypeError("{} mass model subtype not recognized"
                                        " for {} component. Only 'dark_matter'"
                                        " or 'baryonic' accepted.".format(
                                        mcomp._subtype, cmp))

            vel = self.kinematic_options.apply_adiabatic_contract(r,
                                                                  vbaryon, vdm)
            vel = self.kinematic_options.apply_pressure_support(r, self, vel)

            return vel

    def simulate_cube(self, nx_sky, ny_sky, dscale, rstep,
                      spec_type, spec_step, spec_start, nspec,
                      spec_unit=u.km/u.s, line_center=None, oversample=1):
        """Simulate an IFU cube of this model set"""

        # Start with a 3D array in the sky coordinate system
        # x and y sizes are user provided so we just need
        # the z size where z is in the direction of the L.O.S.
        # We'll just use the maximum of the given x and y
        nx_sky_samp = nx_sky*oversample
        ny_sky_samp = ny_sky*oversample
        rstep_samp = rstep/oversample
        nz_sky_samp = np.max([nx_sky_samp, ny_sky_samp])

        # Create 3D arrays of the sky pixel coordinates
        sh = (nz_sky_samp, ny_sky_samp, nx_sky_samp)
        zsky, ysky, xsky = np.indices(sh)
        zsky = zsky - (nz_sky_samp - 1) / 2.
        ysky = ysky - (ny_sky_samp - 1) / 2.
        xsky = xsky - (nx_sky_samp - 1) / 2.

        # Apply the geometric transformation to get galactic coordinates
        xgal, ygal, zgal = self.geometry(xsky, ysky, zsky)

        # The circular velocity at each position only depends on the radius
        # Convert to kpc
        rgal = np.sqrt(xgal ** 2 + ygal ** 2) * rstep_samp / dscale
        vcirc = self.velocity_profile(rgal)

        # L.O.S. velocity is then just vcirc*sin(i)*cos(theta) where theta
        # is the position angle in the plane of the disk
        # cos(theta) is just xgal/rgal
        vobs = (vcirc * np.sin(np.radians(self.geometry.inc.value)) *
                xgal / (rgal / rstep_samp * dscale))
        vobs[rgal == 0] = 0.

        # Calculate "flux" for each position
        flux = np.zeros(vobs.shape)
        for cmp in self.light_components:
            if self.light_components[cmp]:
                zscale = self.zprofile(zgal * rstep_samp / dscale)
                flux += self.components[cmp].mass_to_light(rgal) * zscale

        # Begin constructing the IFU cube
        spec = np.arange(nspec) * spec_step + spec_start
        if spec_type == 'velocity':
            vx = (spec*spec_unit).to(u.km/u.s).value
        elif spec_type == 'wavelength':
            if line_center is None:
                raise ValueError("line_center must be provided if spec_type is "
                                 "'wavelength.'")
            vx = (spec - line_center)/line_center*apy_con.c.to(u.km/u.s).value

        velcube = np.tile(np.resize(vx, (nspec, 1, 1)),
                          (1, ny_sky_samp, nx_sky_samp))
        cube_final = np.zeros((nspec, ny_sky_samp, nx_sky_samp))

        # The final spectrum will be a flux weighted sum of Gaussians at each
        # velocity along the line of sight.
        sigmar = self.dispersion_profile(rgal)
        for zz in range(nz_sky_samp):
            f_cube = np.tile(flux[zz, :, :], (nspec, 1, 1))
            vobs_cube = np.tile(vobs[zz, :, :], (nspec, 1, 1))
            sig_cube = np.tile(sigmar[zz, :, :], (nspec, 1, 1))
            tmp_cube = np.exp(
                -0.5 * ((velcube - vobs_cube) / sig_cube) ** 2)
            cube_sum = np.nansum(tmp_cube, 0)
            cube_sum[cube_sum == 0] = 1
            cube_final += tmp_cube / cube_sum * 100. * f_cube

        return cube_final, spec


# ***** Mass Component Model Classes ******
# Base abstract mass model component class
class _DysmalModel(Model):

    parameter_constraints = DysmalParameter.constraints

    @property
    def prior(self):
        return self._constraints['prior']


class _DysmalFittable1DModel(_DysmalModel):

    linear = False
    fit_deriv = None
    col_fit_deriv = True
    fittable = True

    inputs = ('x',)
    outputs = ('y',)


class MassModel(_DysmalFittable1DModel):

    _type = 'mass'

    @abc.abstractmethod
    def enclosed_mass(self, *args, **kwargs):
        """Evaluate the enclosed mass as a function of radius"""

    def circular_velocity(self, r):
        """
        Default method to evaluate the circular velocity
        as a function of radius using the standard equation:
        v(r) = SQRT(GM(r)/r)
        """

        mass_enc = self.enclosed_mass(r)
        vcirc = np.sqrt(G.cgs.value * mass_enc * Msun.cgs.value /
                        (r * 1000. * pc.cgs.value))
        vcirc = vcirc/1e5

        return vcirc


class Sersic(MassModel):
    """
    1D Sersic mass model with parameters defined by the total mass,
    Sersic index, and effective radius.
    """

    total_mass = DysmalParameter(default=1, bounds=(5, 14))
    r_eff = DysmalParameter(default=1, bounds=(0, 50))
    n = DysmalParameter(default=1, bounds=(0, 8))

    _subtype = 'baryonic'

    def __init__(self, total_mass, r_eff, n, invq=1.0, noord_flat=False,
                 **kwargs):
        self.invq = invq
        self.noord_flat = noord_flat
        super(Sersic, self).__init__(total_mass, r_eff, n, **kwargs)

    @staticmethod
    def evaluate(r, total_mass, r_eff, n):
        """
        1D Sersic profile parameterized by the total mass and
        effective radius
        """

        return sersic_mr(r, 10**total_mass, n, r_eff)

    def enclosed_mass(self, r):
        """
        Calculate the enclosed mass as a function of radius
        :param r: Radii at which to calculate the enclosed mass
        :return: 1D enclosed mass profile
        """

        return sersic_menc(r, 10**self.total_mass, self.n, self.r_eff)

    def circular_velocity(self, r):

        if self.noord_flat:

            vcirc = apply_noord_flat(r, self.r_eff, 10**self.total_mass,
                                     self.n, self.invq)

        else:

            vcirc = super(Sersic, self).circular_velocity(r)

        return vcirc

    def mass_to_light(self, r):

        return sersic_mr(r, 1.0, self.n, self.r_eff)


class DiskBulge(MassModel):
    """Class with a combined disk and bulge to allow varying of B/T and the
    total baryonic mass"""

    total_mass = DysmalParameter(default=10, bounds=(5, 14))
    r_eff_disk = DysmalParameter(default=1, bounds=(0, 50))
    n_disk = DysmalParameter(default=1, fixed=True, bounds=(0, 8))
    r_eff_bulge = DysmalParameter(default=1, bounds=(0, 50))
    n_bulge = DysmalParameter(default=4., fixed=True, bounds=(0, 8))
    bt = DysmalParameter(default=0.2, bounds=(0, 1))

    _subtype = 'baryonic'

    def __init__(self, total_mass, r_eff_disk, n_disk, r_eff_bulge,
                 n_bulge, bt, invq_disk=5, invq_bulge=1, noord_flat=False,
                 light_component='disk', **kwargs):

        self.invq_disk = invq_disk
        self.invq_bulge = invq_bulge
        self.noord_flat = noord_flat
        self.light_component = light_component

        super(DiskBulge, self).__init__(total_mass, r_eff_disk, n_disk,
                                        r_eff_bulge, n_bulge, bt, **kwargs)

    @staticmethod
    def evaluate(r, total_mass, r_eff_disk, n_disk, r_eff_bulge, n_bulge, bt):

        mbulge_total = 10**total_mass*bt
        mdisk_total = 10**total_mass*(1 - bt)

        mr_bulge = sersic_mr(r, mbulge_total, n_bulge, r_eff_bulge)
        mr_disk = sersic_mr(r, mdisk_total, n_disk, r_eff_disk)

        return mr_bulge+mr_disk

    def enclosed_mass(self, r):

        mbulge_total = 10 ** self.total_mass * self.bt
        mdisk_total = 10 ** self.total_mass * (1 - self.bt)

        menc_bulge = sersic_menc(r, mbulge_total, self.n_bulge,
                                 self.r_eff_bulge)
        menc_disk = sersic_menc(r, mdisk_total, self.n_disk,
                                self.r_eff_disk)

        return menc_disk+menc_bulge

    def circular_velocity(self, r):

        mbulge_total = 10**self.total_mass*self.bt
        mdisk_total = 10**self.total_mass*(1-self.bt)

        if self.noord_flat:

            vbulge = apply_noord_flat(r, self.r_eff_bulge, mbulge_total,
                                     self.n_bulge, self.invq_bulge)
            vdisk = apply_noord_flat(r, self.r_eff_disk, mdisk_total,
                                     self.n_disk, self.invq_disk)

            vcirc = np.sqrt(vbulge**2 + vdisk**2)

        else:

            vcirc = super(DiskBulge, self).circular_velocity(r)

        return vcirc

    def mass_to_light(self, r):

        if self.light_component == 'disk':

            flux = sersic_mr(r, 1.0, self.n_disk, self.r_eff_disk)

        elif self.light_component == 'bulge':

            flux = sersic_mr(r, 1.0, self.n_bulge, self.r_eff_bulge)

        elif self.light_component == 'total':

            flux_disk = sersic_mr(r, 1.0-self.bt,
                                  self.n_disk, self.r_eff_disk)
            flux_bulge = sersic_mr(r, self.bt,
                                  self.n_bulge, self.r_eff_bulge)
            flux = flux_disk + flux_bulge

        else:

            raise ValueError("light_component can only be 'disk', 'bulge', "
                             "or 'total.'")

        return flux


class NFW(MassModel):
    """
    1D NFW mass model parameterized by the virial radius, virial mass, and
    concentration.
    """

    mvirial = DysmalParameter(default=1.0, bounds=(5, 20))
    conc = DysmalParameter(default=5.0, bounds=(1, 40))

    _subtype = 'dark_matter'

    def __init__(self, mvirial, conc, z=0, cosmo=_default_cosmo,
                 **kwargs):
        self.z = z
        self.cosmo = cosmo
        super(NFW, self).__init__(mvirial, conc, **kwargs)

    def evaluate(self, r, mvirial, conc):
        """1D NFW model for a dark matter halo"""

        rvirial = self.calc_rvir()
        rho0 = self.calc_rho0()

        return (2*np.pi * rho0 * rvirial /
                conc / (1+conc * r / rvirial)**2)

    def enclosed_mass(self, r):
        """
        Calculate the enclosed mass as a function of radius
        :param r: Radii at which to calculate the enclosed mass
        :return: 1D enclosed mass profile
        """

        rho0 = self.calc_rho0()
        rvirial = self.calc_rvir()
        rs = rvirial/self.conc
        aa = 4.*np.pi*rho0*rvirial**3/self.conc**3
        # For very small r, bb can be negative.
        bb = np.abs(np.log((rs + r)/rs) - r/(rs + r))

        return aa*bb

    def calc_rho0(self):

        rvirial = self.calc_rvir()
        aa = 10**self.mvirial/(4.*np.pi*rvirial**3)
        bb = self.conc**3/(np.log(1.+self.conc) - (self.conc/(1.+self.conc)))

        return aa * bb

    def calc_rvir(self):
        """
        Calculate the virial radius based on virial mass and redshift
        M_vir = 100*H(z)^2/G * R_vir^3
        """
        g_new_unit = G.to(u.pc / u.Msun * (u.km / u.s) ** 2).value
        hz = self.cosmo.H(self.z).value
        rvir = ((10 ** self.mvirial * (g_new_unit * 1e-3) /
                (10 * hz * 1e-3) ** 2) ** (1. / 3.))

        return rvir


# ****** Geometric Model ********
class _DysmalFittable3DModel(_DysmalModel):

    linear = False
    fit_deriv = None
    col_fit_deriv = True
    fittable = True

    inputs = ('x', 'y', 'z')
    outputs = ('xp', 'yp', 'zp')

    @property
    def prior(self):
        return self._constraints['prior']


class Geometry(_DysmalFittable3DModel):
    """
    Class to hold the geometric parameters that can be fit.
    Also takes as input the sky coordinates and returns the
    corresponding galaxy plane coordinates.
    """

    inc = DysmalParameter(default=45.0, bounds=(0, 90))
    pa = DysmalParameter(default=0.0, bounds=(-180, 180))
    xshift = DysmalParameter(default=0.0)
    yshift = DysmalParameter(default=0.0)

    _type = 'geometry'

    @staticmethod
    def evaluate(x, y, z, inc, pa, xshift, yshift):

        inc = np.pi / 180. * inc
        pa = np.pi / 180. * (pa - 90.)

        # Apply the shifts in the sky system
        xsky = x - xshift
        ysky = y - yshift
        zsky = z

        xtmp = xsky * np.cos(pa) + ysky * np.sin(pa)
        ytmp = -xsky * np.sin(pa) + ysky * np.cos(pa)
        ztmp = zsky

        xgal = xtmp
        ygal = ytmp * np.cos(inc) - ztmp * np.sin(inc)
        zgal = ytmp * np.sin(inc) + ztmp * np.cos(inc)

        return xgal, ygal, zgal


# ******* Dispersion Profiles **************
class DispersionProfile(_DysmalFittable1DModel):
    """Base dispersion profile model class"""
    _type = 'dispersion'


class DispersionConst(DispersionProfile):

    sigma0 = DysmalParameter(default=10., bounds=(0, None), fixed=True)

    @staticmethod
    def evaluate(r, sigma0):

        return np.ones(r.shape)*sigma0


# ******* Z-Height Profiles ***************
class ZHeightProfile(_DysmalFittable1DModel):
    """Base z-height profile model class"""
    _type = 'zheight'


class ZHeightGauss(ZHeightProfile):

    sigmaz = DysmalParameter(default=1.0, fixed=True, bounds=(0, 10))

    def __init__(self, sigmaz, **kwargs):
        super(ZHeightGauss, self).__init__(sigmaz, **kwargs)

    @staticmethod
    def evaluate(z, sigmaz):
        return np.exp(-0.5*(z/sigmaz)**2)


# ****** Kinematic Options Class **********
class KinematicOptions:
    """
    A simple container for holding the settings for different
    options for calculating the kinematics of a galaxy. Also
    has methods for applying these options.
    """

    def __init__(self, adiabatic_contract=False, pressure_support=False,
                 pressure_support_re=None):
        self.adiabatic_contract = adiabatic_contract
        self.pressure_support = pressure_support
        self.pressure_support_re = pressure_support_re

    def apply_adiabatic_contract(self, r, vbaryon, vhalo):

        if self.adiabatic_contract:
            logger.info("Applying adiabatic contraction.")
            rprime_all = np.zeros(len(r))
            for i in range(len(r)):
                result = scp_opt.newton(_adiabatic, r[i] + 1.,
                                        args=(r[i], vhalo, r, vbaryon[i]))
                rprime_all[i] = result

            vhalo_adi_interp = scp_interp.interp1d(r, vhalo,
                                                   fill_value='extrapolate')
            vhalo_adi = vhalo_adi_interp(rprime_all)
            vel = np.sqrt(vhalo_adi ** 2 + vbaryon ** 2)

        else:

            vel = np.sqrt(vhalo ** 2 + vbaryon ** 2)

        return vel

    def apply_pressure_support(self, r, model, vel):

        if self.pressure_support:

            if self.pressure_support_re is None:
                pre = None
                for cmp in model.mass_components:
                    if model.mass_components[cmp]:
                        mcomp = model.components[cmp]
                        if mcomp._subtype == 'baryonic':
                            if isinstance(mcomp, DiskBulge):
                                pre = mcomp.r_eff_disk.value
                            else:
                                pre = mcomp.r_eff.value
                            break

                if pre is None:
                    logger.warning("No baryonic mass component found. Using "
                                   "1 kpc as the pressure support effective"
                                   " radius")
                    pre = 1.0

            else:
                pre = self.pressure_support_re

            if model.dispersion_profile is None:
                raise AttributeError("Can't apply pressure support without "
                                     "a dispersion profile!")

            #logger.info("Applying pressure support with effective radius of {} "
            #            "kpc.".format(pre))
            sigma = model.dispersion_profile(r)
            vel_squared = (
                vel ** 2 - 3.36 * (r / pre) * sigma ** 2)
            vel_squared[vel_squared < 0] = 0.
            vel = np.sqrt(vel_squared)

        return vel


def _adiabatic(rprime, r_adi, adia_v_dm, adia_x_dm, adia_v_disk):

    if rprime < 0.:
        rprime = 0.1
    if rprime < adia_x_dm[1]:
        rprime = adia_x_dm[1]
    rprime_interp = scp_interp.interp1d(adia_x_dm, adia_v_dm,
                                        fill_value="extrapolate")
    result = (r_adi + r_adi * ((r_adi*adia_v_disk**2) /
                               (rprime*(rprime_interp(rprime))**2)) - rprime)
    return result
