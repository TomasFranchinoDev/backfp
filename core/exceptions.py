class ImportacionError(Exception):
	"""Base para errores de importación controlados."""


class ImportacionDataError(ImportacionError):
	"""Errores esperables por contenido o estructura del archivo."""


class ImportacionSystemError(ImportacionError):
	"""Errores inesperados del sistema que deben llegar al log y cortar el proceso."""
