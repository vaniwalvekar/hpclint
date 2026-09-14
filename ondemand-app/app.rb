# hpclint OnDemand app — a thin web wrapper around `hpclint check`.
#
# This follows the standard OnDemand "sys app" pattern: a small Sinatra
# app running as the logged-in user's own PUN, shelling out to a real
# command-line tool and rendering its output as HTML.
#
# UNTESTED against a real OnDemand server — built as a prototype per the
# project's plan to verify infrastructure pieces at the end, once more of
# the roadmap is built. The core logic it wraps (`hpclint check`) is
# already tested; what needs verifying here is the OnDemand plumbing
# itself (routing, PUN permissions, Passenger startup).

require "sinatra"
require "open3"

# Default path to the Libra config bundled with this app. Adjust if the
# actual install location differs once this is deployed for real.
LIBRA_CONFIG = File.join(File.dirname(__FILE__), "configs", "libra.yaml")

get "/" do
  erb :form
end

post "/check" do
  script_path = params[:script_path].to_s.strip

  if script_path.empty?
    @error = "Please provide a path to a job script."
    return erb :form
  end

  unless File.exist?(script_path)
    @error = "No file found at '#{script_path}'. Check the path and try again."
    return erb :form
  end

  # Shell out to the real, already-tested hpclint command — this app is
  # deliberately a thin wrapper, not a reimplementation of the logic.
  stdout, stderr, status = Open3.capture3("hpclint", "check", script_path, "--config", LIBRA_CONFIG)

  @output = stdout
  @error_output = stderr
  @exit_status = status.exitstatus

  erb :result
end
