#!/usr/bin/env python3
# -*- coding:utf-8 -*-

#############################################
# File Name: setup.py
# Author: CK
# Mail: txq0917@gmail.com
# Created Time:  2021-4-24
#############################################

from setuptools import setup, find_packages
from auto_cut_audio.__version__ import __version__

setup(
    name="auto_cut_audio",
    version=__version__,
    keywords=("pip3", "henry"),
    description="tools for auto cut wav audio",
    long_description="tools for wav audio,you can get audio info,auto cut audio,get audio base noise, delete empty "
                     "noise and so on",
    license="GPL Licence",

    url="https://github.com/code-killerr/Auto_Cut_Audio",
    author="Allen.tu(ck.tu)",
    author_email="txq0917@gmail.com",

    packages=find_packages(),
    include_package_data=True,
    platforms="any",
    install_requires=['numpy']
)
