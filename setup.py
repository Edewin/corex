from setuptools import setup, find_packages

setup(
    name='corex',
    version='1.0.0',
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
