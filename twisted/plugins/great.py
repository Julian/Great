from __future__ import absolute_import
import argparse

from minion.twisted import MinionResource
from pi.utils import Redirect, argparseToOptions
from twisted.application.internet import StreamServerEndpointService
from twisted.internet import reactor
from twisted.internet.endpoints import serverFromString
from twisted.application.service import IServiceMaker, MultiService
from twisted.plugin import IPlugin
from twisted.python.filepath import FilePath
from twisted.web import server
from twisted.web.resource import Resource
from twisted.web.static import File
from zope.interface import implementer

from great.views.core import create_app
import great


parser = argparse.ArgumentParser()
parser.add_argument(
    "endpoint",
    metavar="port",
    help="A strports port to run on",
    type=lambda strport : serverFromString(reactor, strport),
)

parser.add_argument(
    "--canonical-url",
    help="The public facing URL that should be used for the Persona audience "
         "and for any redirects.",
)
parser.add_argument(
    "--redirect", "-r",
    action="append",
    dest="redirects",
    type=lambda strport : serverFromString(reactor, strport),
    help="An endpoint to HTTP 301 redirect to the main port "
         "specified with --port. May be specified multiple times.",
)


@implementer(IPlugin, IServiceMaker)
class GreatServiceMaker(object):
    tapname = "great"
    description = "Start the Great service."
    options = argparseToOptions(parser)

    def makeService(self, options):
        greatPath = FilePath(great.__file__).parent()
        staticPath = greatPath.child("static")

        rootResource = Resource()
        rootResource.putChild("", File(staticPath.child("index.html").path))
        rootResource.putChild("static", File(staticPath.path))

        rootResource.putChild("great", MinionResource(create_app()))

        greatService = StreamServerEndpointService(
            endpoint=options["endpoint"],
            factory=server.Site(rootResource),
        )

        redirects = options["redirects"]
        if not redirects:
            return greatService

        service = MultiService()
        greatService.setServiceParent(service)

        for redirect in redirects:
            redirectService = StreamServerEndpointService(
                endpoint=redirect,
                factory=server.Site(Redirect(options["canonical_url"])),
            )
            redirectService.setServiceParent(service)

        return service


serviceMaker = GreatServiceMaker()
