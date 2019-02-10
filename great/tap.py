from __future__ import absolute_import

from filesystems import Path
from minion.twisted import MinionResource
from twisted.application import strports
from twisted.python import usage
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
        root = Path.from_string(__file__).sibling("alembic")
        alembic_config = alembic.config.Config(
            str(root.descendant("config.ini")),
        )
        alembic.command.upgrade(alembic_config, "head")

    greatPath = Path.from_string(great.__file__).parent()
    staticPath = greatPath.descendant("static")
    templatesPath = greatPath.descendant("templates")

    rootResource = twisted.web.resource.Resource()
    rootResource.putChild("", File(str(staticPath.descendant("index.html"))))
    rootResource.putChild("static", File(str(staticPath)))
    rootResource.putChild("api", MinionResource(create_app()))

    site = server.Site(rootResource)
    return strports.service(description=options["port"], factory=site)
