from open_legis.api.schemas import ErrorResponse, RateLimitResponse

# Common error responses applied to all routes
COMMON_ERRORS: dict = {
    400: {"model": ErrorResponse, "description": "Bad request — invalid parameter value."},
    404: {"model": ErrorResponse, "description": "Resource not found."},
    429: {"model": RateLimitResponse, "description": "Rate limit exceeded. See rate limits table in the API description."},
}

# ELI-specific extras
ELI_ERRORS: dict = {
    **COMMON_ERRORS,
    406: {"model": ErrorResponse, "description": "No AKN expression available for this work."},
}
