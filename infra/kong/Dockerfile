# Kong gateway image for the Render staging Blueprint (render.yaml).
#
# Local development mounts kong.yml as a read-only volume (docker-compose.yml).
# Render has no volume mounts, so the declarative config has to be baked into
# the image instead. Everything else — routing, rate limits, JWT, the /admin
# IP restriction — comes from kong.yml unchanged.
#
# Build context is infra/kong/ (set via `rootDir` in render.yaml).
#
# NOT used in production: production templates kong.yml against the real
# secret store at deploy time rather than shipping it inside an image.

FROM kong:3.7

USER root

COPY kong.yml /etc/kong/kong.yml
RUN chown kong:kong /etc/kong/kong.yml

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
