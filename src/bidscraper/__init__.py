"""bidscraper: generic framework for scraping and normalizing municipal/gov bid-award history.

This is the free/course/public package. It knows nothing about any
specific client, scraping target, or hosting provider -- those belong in
a downstream deployment package (e.g. a paid "full" overlay) that depends
on this one.
"""

import truststore

# Use the OS-native certificate trust store for all outbound HTTPS made by
# this process (scraper HTTP requests, the Anthropic API client, Postgres
# driver, etc.) instead of the bundled `certifi` CA list. This matters on
# machines where a local antivirus/endpoint-security product does HTTPS
# inspection (observed with Avast during development) -- the OS trust
# store already has that product's locally-generated root certificate
# installed (that's how every browser keeps working), but `certifi`'s
# bundled list doesn't, so anything relying on it fails TLS verification
# even though the traffic itself is fine. This is a safe default
# everywhere, not just on intercepted networks: it's a superset of the
# public CAs `certifi` ships. Done here, in the package's top-level
# `__init__.py`, so it fires for `import bidscraper` or any
# `from bidscraper.X import Y`, before any of this package's own network
# code can run -- no per-entrypoint-script setup required.
truststore.inject_into_ssl()

__version__ = "0.1.0"
