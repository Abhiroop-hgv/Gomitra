"""Request dependencies: the two shared secrets. Admin routes need `x-admin-key`; the Raspberry Pi route needs `x-device-key`."""
from fastapi import Header

from gomitra import config
from gomitra.errors import Forbidden


def require_admin(x_admin_key: str = Header("")):
    if not config.ADMIN_KEY or x_admin_key != config.ADMIN_KEY:
        raise Forbidden("admin key required")


def require_device(x_device_key: str = Header("")):
    if not config.DEVICE_KEY or x_device_key != config.DEVICE_KEY:
        raise Forbidden("device key required")
