"""Service configuration constants."""

# Maximum number of pooled database connections. Raising this is one fix for
# pool exhaustion under load.
POOL_SIZE = 4

# Seconds before an idle connection is reclaimed.
IDLE_TIMEOUT = 30

# Feature flags.
ENABLE_HEALTHCHECK = True
