import logging


def configure_logging() -> None:
    # Application events contain only fixed messages and generated request IDs.
    logger = logging.getLogger("accounting_office")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
