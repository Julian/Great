from __future__ import absolute_import

from minion.twisted import MinionResource
from twisted.application import strports
from twisted.python import usage
from twisted.python.filepath import FilePath
from twisted.web import server
from twisted.web.static import File
import alembic
import alembic.config
import twisted.web.resource

from great.web import create_app
import great


class Options(usage.Options):
    optFlags = [
        [
            "migrate",
            "",
            "Run `alembic upgrade head` first to migrate the DB if necessary.",
        ],
    ]
    optParameters = [
        [
            "access-log",
            "l",
            None,
            "Path to web CLF (Combined Log Format) log file for access logs.",
        ],
        ["port", "p", "tcp:8080", "The endpoint to listen on."],
    ]


def makeService(options):
    if options["migrate"]:
        alembic_config = alembic.config.Config(FilePath("alembic.ini").path)
        alembic.command.upgrade(alembic_config, "head")

    greatPath = FilePath(great.__file__).parent()
    staticPath = greatPath.child("static")
    templatesPath = greatPath.child("templates")

    rootResource = twisted.web.resource.Resource()
    rootResource.putChild("", File(staticPath.child("index.html").path))
    rootResource.putChild("static", File(staticPath.path))
    rootResource.putChild("templates", File(templatesPath.path))

    rootResource.putChild("great", MinionResource(create_app()))

    site = server.Site(rootResource)
    return strports.service(description=options["port"], factory=site)
