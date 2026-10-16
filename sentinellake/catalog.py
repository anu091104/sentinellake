"""The fictional microservice estate that SentinelLake monitors.

Every generated log line belongs to one of these endpoints. Keeping the catalog in
one place means the generator, the detectors and the docs all agree on what
"normal" looks like.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    service: str
    method: str
    path: str
    weight: float          # share of total traffic (normalised at load time)
    median_ms: float       # typical latency
    p5xx: float = 0.004    # baseline server-error probability
    p4xx: float = 0.02     # baseline client-error probability

    @property
    def name(self) -> str:
        return f"{self.method} {self.path}"


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("auth", "POST", "/v1/token", 0.08, 45),
    Endpoint("auth", "GET", "/v1/me", 0.07, 25),
    Endpoint("catalog", "GET", "/v1/products", 0.14, 60),
    Endpoint("catalog", "GET", "/v1/products/{id}", 0.12, 35),
    Endpoint("search", "GET", "/v1/search", 0.13, 120),
    Endpoint("inventory", "GET", "/v1/stock", 0.08, 30),
    Endpoint("inventory", "PUT", "/v1/stock", 0.02, 70),
    Endpoint("checkout", "POST", "/v1/cart", 0.07, 80),
    Endpoint("checkout", "POST", "/v1/checkout", 0.04, 220, p5xx=0.006),
    Endpoint("payments", "POST", "/v1/charge", 0.035, 350, p5xx=0.006),
    Endpoint("payments", "POST", "/v1/refund", 0.005, 300),
    Endpoint("orders", "GET", "/v1/orders", 0.06, 90),
    Endpoint("orders", "GET", "/v1/orders/{id}", 0.05, 40),
)

REGIONS = ("ap-south-1", "ap-southeast-1", "eu-west-1", "us-east-1")
REGION_WEIGHTS = (0.55, 0.15, 0.12, 0.18)

CLIENT_4XX = (400, 401, 404, 429)
CLIENT_4XX_WEIGHTS = (0.35, 0.25, 0.30, 0.10)
SERVER_5XX = (500, 502, 503, 504)
SERVER_5XX_WEIGHTS = (0.40, 0.15, 0.30, 0.15)

SERVICES = tuple(sorted({e.service for e in ENDPOINTS}))


def by_key(service: str, endpoint: str) -> Endpoint:
    for e in ENDPOINTS:
        if e.service == service and e.name == endpoint:
            return e
    raise KeyError(f"{service} {endpoint}")
