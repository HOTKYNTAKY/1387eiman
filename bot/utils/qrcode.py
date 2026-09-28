"""ساخت QR کد (PNG) برای کانفیگ‌ها و لینک‌های ساب‌اسکریپشن."""

from __future__ import annotations

import io
import logging

import segno

log = logging.getLogger(__name__)


def make_qr_png(data: str, scale: int = 6) -> bytes | None:
    """
    تصویر PNG کد QR را برمی‌گرداند.
    اگر متن برای QR خیلی طولانی باشد None برمی‌گرداند.
    """
    try:
        qr = segno.make(data, error="m", micro=False)
    except segno.DataOverflowError:
        log.debug("QR data too long (%d chars)", len(data))
        return None
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=scale, border=2)
    return buffer.getvalue()
