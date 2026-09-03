import os


os.environ["GREENLINE_MODE"] = "local"
os.environ.pop("CLERK_SECRET_KEY", None)
os.environ.pop("CLERK_AUTHORIZED_PARTIES", None)
