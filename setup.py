import re
from pathlib import Path

from setuptools import setup, find_packages

VERSION = re.search(r'__version__ = "([^"]+)"', Path("corex/__init__.py").read_text()).group(1)

setup(
    name='corex',
    version=VERSION,
    packages=find_packages(),
    package_data={
        'corex': ['assets/**/*'],
    },
    entry_points={
        'console_scripts': [
            'corex=corex.main:main',
        ],
    },
)
