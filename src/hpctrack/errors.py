class TrackError(Exception):
    def __init__(self, error, message, code=1, **details):
        super().__init__(message)
        self.code = code
        self.result = {"ok": False, "error": error, "message": message, **details}


def auth_required(machine, backend="ssh"):
    fix = f"hpctrack connect {machine}" if backend == "ssh" else "alcf-tokens login iri"
    return TrackError(
        "auth_required", f"{backend} authentication required", 20, machine=machine, fix=fix
    )
