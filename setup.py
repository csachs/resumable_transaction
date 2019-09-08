# -*- coding: utf-8 -*-
"""
documentation
"""

from setuptools import setup, find_packages


setup(
    name='resumable_transaction',
    version='0.0.1.dev1',
    description='resumable transactions',
    long_description=
    'A little library allowing for a set of calls to be serialized and re-run later on manually if errors occur.',
    author='Christian C. Sachs',
    author_email='sachs.christian@gmail.com',
    url='https://github.com/csachs/resumable_transaction',
    install_requires=['jsonpickle'],
    packages=find_packages(),
    data_files=[],
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3'
    ]
)
