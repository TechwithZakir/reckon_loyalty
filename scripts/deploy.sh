#!/usr/bin/env bash
# Install or update reckon_loyalty on a bench, as the bench user.
#
#   SITE=distribution.reckon.tech ARCHIVE=/tmp/reckon_loyalty.tgz ./deploy.sh          # install or update
#   SITE=distribution.reckon.tech ARCHIVE=/tmp/reckon_loyalty.tgz SEED=1 ./deploy.sh   # and seed the Sailor demo
#
# ARCHIVE is a tar.gz of this repository. Leave it unset when the app is already in
# apps/reckon_loyalty (for example after `bench get-app`).
# The script backs the site up first. It does not restart services: do that at the end
# (the last line printed tells you how), because a restart briefly affects every site on the bench.
set -euo pipefail

BENCH_DIR="${BENCH_DIR:-$HOME/frappe-bench}"
SITE="${SITE:?Set SITE to the site name}"
ARCHIVE="${ARCHIVE:-}"
SEED="${SEED:-0}"
APP=reckon_loyalty

fail() { echo "DEPLOY STOPPED: $1" >&2; exit 1; }

cd "$BENCH_DIR" || fail "BENCH_DIR $BENCH_DIR does not exist."
[ -d "sites/$SITE" ] || fail "Site $SITE is not on this bench."
[ -d apps/erpnext ] || fail "ERPNext is not on this bench."

echo "Backing up $SITE"
bench --site "$SITE" backup

if [ -n "$ARCHIVE" ]; then
  [ -f "$ARCHIVE" ] || fail "Archive $ARCHIVE not found."
  mkdir -p "apps/$APP"
  tar -xzf "$ARCHIVE" -C "apps/$APP"
fi
[ -f "apps/$APP/pyproject.toml" ] || fail "apps/$APP is missing. Pass ARCHIVE or run bench get-app first."

# bench expects every app to be a git repository.
if [ ! -d "apps/$APP/.git" ]; then
  git -C "apps/$APP" init -q -b main
fi
git -C "apps/$APP" add -A
git -C "apps/$APP" -c user.name=deploy -c user.email=deploy@localhost commit -q -m "Deploy $(date +%F-%H%M)" || true

./env/bin/pip install -q -e "apps/$APP"
if ! grep -qx "$APP" sites/apps.txt; then
  cp sites/apps.txt "sites/apps.txt.before-$APP-$(date +%Y%m%d%H%M)"
  # Make sure the file ends with a newline before appending.
  [ -z "$(tail -c1 sites/apps.txt)" ] || echo >> sites/apps.txt
  echo "$APP" >> sites/apps.txt
fi

if bench --site "$SITE" list-apps | grep -q "^$APP"; then
  echo "Migrating $SITE"
  bench --site "$SITE" migrate
else
  echo "Installing $APP on $SITE"
  bench --site "$SITE" install-app "$APP"
fi

bench build --app "$APP"
bench --site "$SITE" clear-cache

if [ "$SEED" = "1" ]; then
  echo "Seeding the Sailor demo company (takes a few minutes)"
  bench --site "$SITE" execute reckon_loyalty.demo.seed.run
fi

echo "Done. Restart the web and worker processes so they load the new app:"
echo "  sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:"
