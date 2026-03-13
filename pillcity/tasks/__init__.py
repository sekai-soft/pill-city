import os
import logging

from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file and sets them in os.environ

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Sentry
if os.getenv("SENTRY_DSN"):
    logging.info("Enabling sentry")
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        # no performance monitoring
        traces_sample_rate=0,
    )
else:
    logging.info("Not enabling sentry")
