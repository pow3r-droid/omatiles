# Publishing OmaTiles

1. Run the checks: `tests/check.sh` must end with every suite passing and `omarchy plugin validate` clean.
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
