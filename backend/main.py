import uvicorn


def main() -> None:
    """Run the development server."""
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
