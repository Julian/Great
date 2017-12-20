from twisted.application.service import ServiceMaker
mux = ServiceMaker(
    name="Great Server Service",
    module="great.tap",
    description="The Great Application Service",
    tapname="great",
)
