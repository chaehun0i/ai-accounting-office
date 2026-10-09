from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(title="AI Accounting Office", version="0.1.0", debug=False)
