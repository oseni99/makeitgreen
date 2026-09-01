class UploadError(RuntimeError):
    pass


class UploadNotFound(UploadError):
    pass


class UploadClosed(UploadError):
    pass


class ChunkConflict(UploadError):
    pass


class IncompleteUpload(UploadError):
    pass


class IntegrityError(UploadError):
    pass
