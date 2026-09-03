#!/bin/bash
# Elasticsearch entrypoint for Railway (SCRUM-203).
#
# Railway mounts every volume owned by root, but the Elasticsearch image runs
# as uid 1000 — so ES cannot create data/node.lock and dies with
# "failed to obtain node locks ... AccessDeniedException".
#
# Railway's documented remedy for that class of failure is RAILWAY_RUN_UID=0,
# which starts the container as root. That alone swaps one crash for another,
# because ES refuses to run as root outright:
#   java.lang.RuntimeException: can not run elasticsearch as root
#
# The image's own TAKE_FILE_OWNERSHIP hook is meant to bridge exactly this gap
# (chown the data dirs, then step down to uid 1000), but 8.13.4's entrypoint
# does not step down — verified on this deployment: it chowned nothing and ES
# still booted as root.
#
# So do both halves explicitly, in the one place that is guaranteed to run
# first. We need root for the chown and non-root for ES itself, and this is
# the only point where both are available in the right order.
#
# `chroot --userspec` is how the upstream image drops privileges too, so this
# is the image's own mechanism rather than a novel one. `chroot /` changes no
# root directory; it is simply the available way to exec as another user
# without gosu/su-exec, neither of which ships in this image.
#
# Requires RAILWAY_RUN_UID=0 on the service. Without it the container starts
# as uid 1000, the chown below fails, and we fall through to running ES as
# 1000 anyway — correct whenever the volume already has the right owner
# (every restart after the first), which is why the chown is not fatal.
set -e

DATA_DIR=/usr/share/elasticsearch/data
LOGS_DIR=/usr/share/elasticsearch/logs

if [ "$(id -u)" = "0" ]; then
  chown -R 1000:0 "$DATA_DIR" "$LOGS_DIR"
  echo "railway-entrypoint: chowned $DATA_DIR and $LOGS_DIR to 1000:0"
  echo "railway-entrypoint: dropping to uid 1000 to start Elasticsearch"
  exec chroot --userspec=1000:0 / /usr/local/bin/docker-entrypoint.sh "$@"
fi

# Already non-root: nothing to fix, hand straight to the stock entrypoint.
echo "railway-entrypoint: running as $(id -u), delegating to docker-entrypoint.sh"
exec /usr/local/bin/docker-entrypoint.sh "$@"
