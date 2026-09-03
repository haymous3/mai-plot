# Elasticsearch 8 for the Railway deployment (SCRUM-203).
#
# Identical to the stock image used by docker-compose.yml — same version, same
# settings — plus one entrypoint wrapper that reconciles Railway's root-owned
# volumes with an image that refuses to run as root. See railway-entrypoint.sh
# for the full reasoning.
#
# This image exists ONLY because the platform needs it. Nothing about the
# search behaviour changes, so listing-service talks to it exactly as it talks
# to the compose container. Keep the version pinned to the one in
# docker-compose.yml so local and deployed search behave the same.
#
# Build context is infra/elasticsearch/ (set via the service root directory).
FROM docker.elastic.co/elasticsearch/elasticsearch:8.13.4

USER root

COPY railway-entrypoint.sh /usr/local/bin/railway-entrypoint.sh
RUN chmod 0755 /usr/local/bin/railway-entrypoint.sh

# Deliberately left as root: the entrypoint needs root to chown the mounted
# volume, and drops to uid 1000 itself before exec'ing Elasticsearch. Setting
# USER elasticsearch here would take away the privilege the fix depends on.

EXPOSE 9200

# Deliberately CMD-only, with no ENTRYPOINT.
#
# Railway does not always preserve an image's ENTRYPOINT: once this service
# had ever been given a start command, it ran the image's CMD as the command
# directly and dropped the ENTRYPOINT — so an ENTRYPOINT/CMD split lost the
# wrapper and tried to exec the bare sentinel `eswrapper`, which is not a
# binary ("The executable `eswrapper` could not be found").
#
# Putting the whole argv in CMD is correct under both interpretations, and
# behaves identically under plain `docker run`.
CMD ["/usr/local/bin/railway-entrypoint.sh", "eswrapper"]
