class PermanentJobError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
