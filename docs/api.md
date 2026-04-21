# API reference

See `/docs` (Swagger) for live docs; this page summarises the surface.

## Resolution (ELI URI → resource)

    GET /eli/bg/{type}/{year}/{slug}
    GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}
    GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}/{element_path}

Content negotiation:

    Accept: application/json        (default — JSON)
    Accept: application/akn+xml     (Akoma Ntoso XML)
    Accept: text/turtle             (ELI RDF / Turtle)

Override via `?format=json|akn|ttl`.

## Discovery

    GET /works?type=&year=&status=
    GET /search?q=&type=
    GET /works/{slug}/amendments?direction=in|out
    GET /works/{slug}/references?direction=in|out
    GET /works/{slug}/expressions

## Aliases (301 to canonical)

    GET /by-dv/{year}/{broy}/{position}
    GET /by-external/{lex_bg|parliament_bg|dv_parliament_bg}/{id}

## Bulk

    GET /dumps/                  JSON list of available snapshots
    GET /dumps/latest.tar.gz
    GET /dumps/latest.sql.gz
