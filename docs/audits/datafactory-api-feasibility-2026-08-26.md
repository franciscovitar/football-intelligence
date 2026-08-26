# DataFactory API feasibility — zero-cost historical Argentina

Status: **NO-GO for zero-cost V1 / reconsider only with explicit provider grant**.

This bounded technical spike asked whether DataFactory's official API could provide historical Argentina player/roster evidence without scraping, credentials, or spend.

## Official documentation

The public Swagger at `https://www.datafactory.la/api/` exposes OpenAPI 3.1.0, API version `0.9.0`, and states that the Feed API is under development and will use an API key for data access.

The OpenAPI server is:

`https://apidev3.datafactory.la:8443`

Documented football endpoints include:

- `GET /api/v1/sports/{sport}/{competition}/fixture`
- `GET /api/v1/sports/{sport}/{competition}/leaders`
- `GET /api/v1/sports/{sport}/{competition}/match/{id}`
- `GET /api/v1/sports/{sport}/{competition}/positions`
- `GET /api/v1/sports/{sport}/{competition}/rosters`
- `GET /api/v1/updates?since=...`

The endpoint descriptions say that fixture, match, positions and roster data are returned in XML. The request definitions include an `X-API-KEY` header described as an access token.

The public OpenAPI does **not** expose a `season` query parameter for `rosters`; it accepts only `sport` and `competition` path values plus headers.

## Runtime probe

GitHub Actions run: `32995946283`.

The first probe captured the public OpenAPI document and established that the WordPress `/api/` path is documentation only. The second bounded probe called the actual OpenAPI server with no credentials.

Observed runtime behavior:

- `GET https://apidev3.datafactory.la:8443/health`
  - HTTP `200`
  - `Content-Type: application/xml`
  - body: `<Health><Status>ok</Status></Health>`
- `GET https://apidev3.datafactory.la:8443/api/v1/updates?since=20241203T16:31:33Z`
  - HTTP `403`
  - `Content-Type: application/xml; charset=UTF-8`
  - provider response: `forbidden_access`
  - detail: `Your API key does not have the necessary permissions to access this information.`

No credentials were used and no attempt was made to bypass authentication.

## Commercial context

DataFactory's public coverage page classifies `Liga de Argentina` as `Premium`. Its public product pages describe sports data/API/XML feeds as products and direct prospects to contact/sales/demo flows. A free historical API tier with reusable bulk data was not found during this audit.

## Decision

DataFactory is technically relevant and historically plausible, especially because it has long-standing Argentina coverage, but it is **not a zero-cost acquisition path under currently verified public access**.

Football Intelligence must not:

- scrape DataFactory presentation pages as a substitute for API access;
- guess or bypass API credentials;
- treat the publicly visible Swagger as permission to retrieve or redistribute protected feed data;
- assume that a free widget/branded-content offer grants access to the underlying historical API feed.

Reconsider DataFactory only if the provider explicitly grants a suitable key/trial **and** confirms:

1. historical Argentina player/roster depth for the target seasons, including early 2016;
2. whether historical data may be stored after access ends;
3. publication/commercial-use rights for Football Intelligence;
4. price after any trial, if applicable.

Until then the source state is:

`rejected_zero_cost_auth_required`
