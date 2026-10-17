import os


os.environ.setdefault("AUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-github-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-github-client-secret")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key")
