---
name: screenshot
description: "Use for screenshots on Blaise's Sway/Wayland desktop."
---

# Screenshot

Clipboard image paste doesn't work reliably here (foot on Sway). The
`$mod+F7` hotkey saves to `~/Pictures/screenshot.png`, overwriting it each
time. When the user mentions "the screenshot", open that file with your
image viewer instead of asking them to paste it. The `Print` key keeps
timestamped copies in `~/Pictures`.

## Taking your own

Use this to check a visual change, such as a waybar or sway config edit,
before reporting it done.

- Full screen: `grim out.png`. One monitor: `grim -o <output> out.png`, with
  names from `swaymsg -t get_outputs`. A region: `grim -g "0,0 1920x30" out.png`.
- One app, even in the background or on another workspace:
  `~/.config/sway/screenshot-app.sh app <name> <query> [out.png]`. `<query>`
  matches app_id, class, or title. It uses `wayshot-git`, captures off-screen
  windows, and never changes focus or workspace.
- A workspace: `~/.config/sway/screenshot-app.sh workspace <name> <ws> [out.png]`.
  This only works if the workspace is visible, and errors otherwise. Ask the
  user to switch to it.
- Run `screenshot-app.sh list` to see the windows and workspaces.

`<name>` is a tag unique to you, such as your task ID. The default output is
`~/Pictures/screenshot-<name>.png`, so parallel agents don't collide. Delete
captures that were only for checking.

GL windows (rviz2, gz sim) can come back solid black in `app` mode. Retry
once, then fall back to a full-screen `grim` capture rather than trusting the
black image.
