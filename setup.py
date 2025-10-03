# setup.py
from setuptools import setup, find_packages

setup(
    name="swapwithus",           # Package name
    version="0.1",               # Version
    packages=find_packages(),    # Automatically find all packages in my_package/
    install_requires=[           # External dependencies
        # "numpy",
        # "pandas",
    ],
    python_requires=">=3.10",
)
