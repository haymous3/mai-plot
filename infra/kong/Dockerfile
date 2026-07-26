# Kong gateway image for the Render Blueprint (render.yaml).
#
# Local development mounts kong.yml as a read-only volume (docker-compose.yml).
# Render has no volume mounts, so the declarative config has to be baked into
# the image instead. Everything else — routing, rate limits, JWT, the /admin
# IP restriction — comes from kong.yml unchanged.
#
# The JWT consumer secret is NOT baked in: kong.yml still carries the dev
# placeholder here, and render-entrypoint.sh substitutes the real value from
# $KONG_JWT_SECRET at container start. So this image contains no secret and is
# safe to rebuild from any branch.
#
# Build context is infra/kong/ (set via `rootDir` in render.yaml).

FROM kong:3.7

USER root

COPY kong.yml /etc/kong/kong.yml
COPY render-entrypoint.sh /usr/local/bin/render-entrypoint.sh

# kong.yml must be writable at runtime — the entrypoint rewrites it in place to
# substitute the JWT secret before Kong loads it.
RUN chown kong:kong /etc/kong/kong.yml \
 && chmod 0644 /etc/kong/kong.yml \
 && chmod 0755 /usr/local/bin/render-entrypoint.sh

USER kong

# DB-less mode. The listen addresses are also set in render.yaml so they stay
# visible next to the service definition; these are the defaults if absent.
ENV KONG_DATABASE=off \
    KONG_DECLARATIVE_CONFIG=/etc/kong/kong.yml \
    KONG_PROXY_LISTEN=0.0.0.0:8000 \
    KONG_ADMIN_LISTEN=127.0.0.1:8001 \
    KONG_PROXY_ACCESS_LOG=/dev/stdout \
    KONG_PROXY_ERROR_LOG=/dev/stderr

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/render-entrypoint.sh"]
CMD ["kong", "docker-start"]
