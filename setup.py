import os

from setuptools import find_packages, setup

from great import __url__


with open(os.path.join(os.path.dirname(__file__), "README.rst")) as readme:
    long_description = readme.read()

classifiers = [
    "Development Status :: 3 - Alpha",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: Implementation :: CPython",
    "Programming Language :: Python :: Implementation :: PyPy"
]

setup(
    name="great",
    packages=find_packages() + ["twisted.plugins"],

    setup_requires=["setuptools_scm"],
    use_scm_version=True,

    install_requires=[
        "Alchimia",
        "alembic",
        "appdirs",
        "attrs",
        "filesystems",
        "hyperlink",
        "Minion",
        "pytoml",
        "SQLAlchemy",
        "Twisted",
        "txmusicbrainz",
    ],
    author="Julian Berman",
    author_email="Julian@GrayVines.com",
    classifiers=classifiers,
    description="A ratings aggregator",
    license="MIT",
    long_description=long_description,
    url=__url__,
)
