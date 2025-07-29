def setup_routes(app, config, services):
    from . import reply

    app.include_router(reply.router, prefix="/reply", tags=["reply"])
    reply.router.config = config
    reply.router.services = services