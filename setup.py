import distutils.command.build
import os
import setuptools

from great import __url__


HERE = os.path.abspath(os.path.dirname(__file__))
FRONTEND = os.path.join(HERE, "frontend")
STATIC = os.path.join(HERE, "great", "static")


class BuildFrontend(setuptools.Command):

    description = "build the Great frontend"
    user_options = []

    def initialize_options(self):
        pass

    def run(self):
        self.spawn(
            [
                "npm",
                "--prefix", FRONTEND,
                "run-script", "build:dev",
                "--",
                "--output-public-path", "/static/",
                "--output-path", STATIC,
            ],
        )

    def finalize_options(self):
        pass


setuptools.setup(
    url=__url__,
    packages=setuptools.find_packages() + ["twisted.plugins"],
    use_scm_version=True,
    cmdclass={
        "build_frontend": BuildFrontend,
    },
)
