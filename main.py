import uvicorn


def main():
    uvicorn.run(
        app="payment_gateway_api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["payment_gateway_api"],
        workers=1,
        log_config=None,
    )


if __name__ == "__main__":
    main()
