Plugin for CudaText.
Plugin provides auto-completion for Bootstrap classes, inside
  class="..."
Supported Bootstrap versions: 2, 3, 4, 5.

For a single caret: completion works as usual. 
For multiple carets: the whole attribute value (quoted) will be replaced
with the chosen item.


Options
-------
Plugin has the option to specify Bootstrap versions to use. Value must be
comma-separated numbers like "4" or "3,4".

1) To set it globally, call "Options / Settings-plugins / Bootstrap Completion / Config",
and write the option to plugins.ini, like this:

[bootstrap_complete]
versions=4

2) To set it per-project, open dialog "Project properties" (in the context menu
of Project Manager), and write the option to the "Variables" field:

bootstrap_complete_versions=4


About
-----
Author: halfbrained (https://github.com/halfbrained)
Credits: 
  Plugin uses completion data from Sublime Text plugin:
  https://github.com/jfcherng-sublime/ST-BootstrapAutocomplete
License: MIT
