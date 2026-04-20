class ServiceError(Exception):
    # Error base da camada de servico (agnostica de HTTP/FastAPI).
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
