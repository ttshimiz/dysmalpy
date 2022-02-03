#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re

import logging
from setuptools.command.build_ext import build_ext
from distutils.errors import CCompilerError, DistutilsExecError, DistutilsPlatformError

try:
    from setuptools import setup, Extension
except:
    from distutils.core import setup, Extension

from Cython.Build import cythonize

dir_path = os.path.dirname(os.path.realpath(__file__))

init_string = open(os.path.join(dir_path, 'dysmalpy', '__init__.py')).read()
VERS = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VERS, init_string, re.M)
__version__ = mo.group(1)


logging.basicConfig()
log = logging.getLogger(__file__)


with open('README.rst') as readme_file:
    readme = readme_file.read()

requirements = ['numpy', 'scipy', 'matplotlib', 'astropy',
                'emcee', 'corner', 'cython', 'dill',
                'shapely', 'spectral-cube', 'radio-beam',
                'h5py', 'pandas', 'six']

setup_requirements = ['Cython', 'numpy']

try:
    # try building with c code :

    setup(
        author="Taro Shimizu & Sedona Price",
        author_email='shimizu@mpe.mpg.de',
        python_requires='>=3.5',
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Science/Research',
            'License :: OSI Approved :: 3-clause BSD',
            'Natural Language :: English',
            "Topic :: Scientific/Engineering",
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
            'Programming Language :: Python :: 3.7',
        ],
        description="A modelling and fitting package for galaxy kinematics.",
        install_requires=requirements,
        setup_requires=setup_requirements,
        license="3-clause BSD",
        long_description=readme,
        include_package_data=True,
        name='dysmalpy',
        packages=['dysmalpy', 'dysmalpy.extern', 'dysmalpy.models', 'dysmalpy.fitting', 'dysmalpy.fitting_wrappers'],
        package_data={'dysmalpy': ['data/noordermeer/*.save']},
        version=__version__,
        ext_modules=cythonize([
                        "dysmalpy/models/cutils.pyx",
                        Extension("dysmalpy.lensingTransformer",
                            sources=["dysmalpy/lensing_transformer/lensingTransformer.cpp"],
                            language="c++",
                            include_dirs=["lensing_transformer", "/usr/include", "/usr/local/include"],
                            libraries=['gsl', 'gslcblas', 'cfitsio'],
                            lib_dirs=["/usr/lib", "/usr/lib/x86_64-linux-gnu", "/usr/local/lib"],
                            depends=["dysmalpy/lensing_transformer/lensingTransformer.hpp"],
                            extra_compile_args=['-std=c++11']
                        ),
                        Extension("dysmalpy.leastChiSquares1D",
                            sources=["dysmalpy/utils_least_chi_squares_1d_fitter/leastChiSquares1D.cpp"],
                            language="c++",
                            include_dirs=["utils_least_chi_squares_1d_fitter", "/usr/include", "/usr/local/include"],
                            libraries=['gsl', 'gslcblas', 'pthread'],
                            lib_dirs=["/usr/lib", "/usr/lib/x86_64-linux-gnu", "/usr/local/lib"],
                            depends=["dysmalpy/utils_least_chi_squares_1d_fitter/leastChiSquares1D.hpp",
                                    "dysmalpy/utils_least_chi_squares_1d_fitter/leastChiSquaresFunctions1D.hpp"],
                            extra_compile_args=['-std=c++11']
                        )
                     ])
    )
#except ext_errors as ex:
except:
    #log.warn(ex)
    log.warn("The C extension could not be compiled")

    # ## Retry to install the module without C extensions :
    # # Remove any previously defined build_ext command class.
    # if 'build_ext' in setup_args['cmdclass']:
    #     del setup_args['cmdclass']['build_ext']

    # If this new 'setup' call don't fail, the module
    # will be successfully installed, without the C extension :

    setup(
        author="Taro Shimizu & Sedona Price",
        author_email='shimizu@mpe.mpg.de',
        python_requires='>=3.5',
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Science/Research',
            'License :: OSI Approved :: 3-clause BSD',
            'Natural Language :: English',
            "Topic :: Scientific/Engineering",
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
            'Programming Language :: Python :: 3.7',
        ],
        description="A modelling and fitting package for galaxy kinematics.",
        install_requires=requirements,
        setup_requires=setup_requirements,
        license="3-clause BSD",
        long_description=readme,
        include_package_data=True,
        name='dysmalpy',
        packages=['dysmalpy', 'dysmalpy.extern', 'dysmalpy.models', 'dysmalpy.fitting', 'dysmalpy.fitting_wrappers'],
        package_data={'dysmalpy': ['data/noordermeer/*.save']},
        version=__version__,
        ext_modules=cythonize(["dysmalpy/models/cutils.pyx"])
    )
    log.info("Plain installation succeeded.")
