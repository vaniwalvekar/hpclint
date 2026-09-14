# hpclint OnDemand app (prototype — untested against a real server)

A minimal Sinatra "sys app" wrapping `hpclint check`, following OSC's
standard pattern for custom OnDemand apps: shell out to a real command,
render its output as HTML.

**Status:** written but not yet deployed or run against a real OnDemand
instance. Per the project's plan, infrastructure pieces like this get
verified end-to-end once more of the roadmap is built — the part being
tested here is the OnDemand plumbing, not `hpclint check` itself (that's
already covered by the main test suite).

## To deploy for real testing (once ready)

1. Copy this whole `ondemand-app/` directory to
   `/var/www/ood/apps/sys/hpclint` on the OnDemand server (needs an
   account with permission to write there — likely DST, not a personal
   account).
2. Ensure `hpclint` itself is installed and on `PATH` for the Passenger
   process (e.g. via the module file in `../modulefiles/`, or a shared venv).
3. Restart Passenger / reload the app (`touch tmp/restart.txt` is the
   usual Passenger convention, exact steps depend on the server's setup).
4. The app should appear as a new tile on the OnDemand Dashboard.

## Known open questions (to resolve when actually testing this)

- Does the OnDemand server have Sinatra/Ruby gems available, or do they
  need bundling?
- Does the PUN (per-user Nginx process) have `hpclint` on its `PATH` by
  default, or does the app need to set that explicitly?
- File path input (typing a path) vs. integrating with OnDemand's actual
  file browser widget — this version uses the simpler text-input approach
  first.
