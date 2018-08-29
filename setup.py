from setuptools import find_packages, setup
from great import __url__
setup(
    url=__url__,
    packages=find_packages() + ["twisted.plugins"],
    use_scm_version=True,
)
