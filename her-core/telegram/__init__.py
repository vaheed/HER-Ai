"""HER Telegram bot package.

Note: this package extends its import path so python-telegram-bot submodules
(e.g., telegram.ext) remain available when running from /app.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
