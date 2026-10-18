# Publishing OmaTiles

1. Run the checks: `tests/check.sh` must end with every suite passing and `omarchy plugin validate` clean.
   Then walk the security checklist below against the diff since the last release.

## Security checklist

The tests only catch what someone thought of. Before each release, follow the user's data across every
boundary the diff touches and answer these. Each finding gets a fix and a test that fails without it.

- **What you see is what runs.** Wherever the user approves something (a store widget, a widget Claude wrote,
  anything new), the approval names exactly what runs: the action carries the SHA-256 of what was shown and
  the backend refuses anything else. The screen refreshes when the data behind it changes.
- **Nothing private on a command line.** Other local users can read a running process's arguments. Chat
  turns, widget requests and anything the user typed go over stdin, at every hop (desk, backend, CLI).
- **Agents write only where they must.** Each agent call gets the fewest tools, a read-only sandbox where it
  has one, and no write access (`--add-dir`, cwd) to the plugin's folder or the user's config.
- **Shell lines are built from checked parts only.** Every value put into a shell line or a hyprctl dispatch
  is validated by a pattern or passed through `shlex.quote`, and has a test with a hostile value.
- **Files stay ours.** Paths derived from ids are matched by a pattern and resolved inside our folders.
  Nothing is written into the plugin's folder at run time (it makes Omarchy reload the plugin).
2. Create the public repository and push:

   ```sh
   gh repo create pow3r-droid/omatiles --public --source . --remote origin \
     --description "A tile desk for Omarchy: clock, calendar, weather, machine cards, agent chats, OWL widgets and a dock" --push
   ```

3. Submit it to the marketplace (github.com/omacom/omarchy-plugin-marketplace, see its SUBMISSION.md):

   ```sh
   cat > /tmp/omatiles-submission.md <<'BODY'
   ### Repository URL

   https://github.com/pow3r-droid/omatiles

   ### Category

   Desktop

   ### Tags

   quickshell, hyprland, ai

   ### Suggest a missing tag

   widgets

   ### Maintainer notes

   Service plugin (keepLoaded) that draws a tile desk on workspaces 1-3. It vendors Simon Schubert's OWL runtime and
   checker (MIT, owl/VENDORED.txt has the commit and the one local patch; owl.jar is the store's checker as its CI runs
   it). systemctl appears only as read-only `list-units` in the machine-card probe. No sudo, no config is overwritten:
   the desk creates ~/.config/omarchy/omatiles.json once and only edits its own layout keys.

   ### Submission checklist

   - [x] The repository is public and contains installation and removal instructions.
   - [x] I have documented the plugin license and any external dependencies.
   - [x] I confirm that I own or have permission to submit this plugin and its preview assets.
   - [x] The plugin does not overwrite user configuration without explicit consent.
   - [x] I understand that approval is for listing and is not a security review.
   BODY
   gh issue create --repo omacom/omarchy-plugin-marketplace --title "[Plugin]: OmaTiles" --body-file /tmp/omatiles-submission.md
   ```

4. After a release: bump `version` in manifest.json, add a CHANGELOG entry, push, and request an update through the
   marketplace's verify form.
