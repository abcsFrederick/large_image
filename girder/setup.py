#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages

with open('../README.rst') as readme_file:
    readme = readme_file.read()


def prerelease_local_scheme(version):
    """
    Return local scheme version unless building on master in CircleCI.

    This function returns the local scheme version number
    (e.g. 0.0.0.dev<N>+g<HASH>) unless building on CircleCI for a
    pre-release in which case it ignores the hash and produces a
    PEP440 compliant pre-release version number (e.g. 0.0.0.dev<N>).
    """
    from setuptools_scm.version import get_local_node_and_date

    if 'CIRCLE_BRANCH' in os.environ and \
       os.environ['CIRCLE_BRANCH'] in ('master', 'girder-3'):
        return ''
    else:
        return get_local_node_and_date(version)


setup(
    name='girder_large_image',
    use_scm_version={'root': '..', 'local_scheme': prerelease_local_scheme},
    setup_requires=['setuptools_scm'],
    description='A Girder plugin to create, serve, and display large multiresolution images.',
    author='Kitware, Inc.',
    author_email='kitware@kitware.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ],
    install_requires=[
        'enum34>=1.1.6',
        'girder>=3.0.0a2',
        'girder-jobs>=3.0.0a2',
        'girder-worker[girder]>=0.5.1.dev213',
        'jsonschema>=2.5.1',
        'large_image>=1.0.0.dev0',
        'ujson>=1.35',
    ],
    extras_require={
        'tasks': [
            'large-image-tasks',
        ],
    },
    include_package_data=True,
    keywords='girder-plugin, large_image',
    license='Apache Software License 2.0',
    long_description=readme,
    packages=find_packages(exclude=['test', 'test.*']),
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
    url='https://github.com/girder/large_image',
    zip_safe=False,
    entry_points={
        'girder.plugin': [
            'large_image = girder_large_image:LargeImagePlugin',
            'large_image_annotation = girder_large_image_annotation:LargeImageAnnotationPlugin'
        ]
    },
)
