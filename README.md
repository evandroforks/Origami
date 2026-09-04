Origami
======
Origami is a new way of thinking about panes in Sublime Text 2 and 3: you tell Sublime Text where you want a new pane, and it makes one for you. It works seamlessly alongside the built-in layout commands.

Ordinarily one uses the commands under View>Layout, or if one is quite intrepid a custom keyboard shortcut can be made to give a specific layout, but both of these solutions were unsatisfactory to me. Perhaps they were to you too! That's what this plugin is for.

Try it out! I think you'll like it.

Keyboard shortcuts
------------------
Origami is driven by keyboard shortcuts. By default, these keyboard shortcuts are all two-stage, and are hidden behind `command+k`. First press `command+k`, then press the arrow keys with modifiers:

* no modifiers: travel to an adjacent pane
* `shift`: carry the current file to the destination
* `alt` (`option`): clone the current file to the destination
* `command`: create an adjacent pane
* `command+shift`: destroy an adjacent pane

These keyboard shortcuts are designed to make it really easy to modify the layout of your editor.

Additionally, Origami allows one to zoom the current pane, making it take up a large portion of the window. As above, first press `command+k`, then press:

* `command+z`: Zoom the current pane so it takes up 90% of the screen (the fraction is changeable in the keybindings)
* `shift+command+z`: Unzoom: equally space all panes

It is also possible to edit the pane sizes. After `command+k` press:
* `command+r`: Adjust the top and bottom separator
* `command+c`: Adjust the left and right separator

In the keybindings you can change a `mode` which specifies which separation lines you want to edit.
* `ALL` means all horizontal (or vertical) separators
* `RELEVANT` means all horizontal (or vertical) separators which intersect the column (row) of the selected row.
* `NEAREST` means top and bottom (or left and right) separators. This is the default `mode`.
* `BEFORE` means top (or left) separator
* `AFTER` means bottom (or right) separator

(Note: Windows and Linux use `ctrl` instead of `command`.)

Automation
----------
You can have Origami automatically zoom the active pane by setting `auto_zoom_on_focus` in your Origami user preferences. Set it to `true` for the default zoom, or set it to a user-definable fraction of the screen, such as `0.75`.

Origami can also automatically close a pane for you once you've closed the last file in it. Just set `auto_close_empty_panes` to true in the Origami preferences.


## Installation

### By Package Control

1. Download & Install **`Sublime Text 3`** (https://www.sublimetext.com/3)
1. Go to the menu **`Tools -> Install Package Control`**, then,
    wait few seconds until the installation finishes up
1. Now,
    Go to the menu **`Preferences -> Package Control`**
1. Type **`Add Channel`** on the opened quick panel and press <kbd>Enter</kbd>
1. Then,
    input the following address and press <kbd>Enter</kbd>
    ```
    https://raw.githubusercontent.com/evandrocoan/StudioChannel/master/channel.json
    ```
1. Go to the menu **`Tools -> Command Palette...
    (Ctrl+Shift+P)`**
1. Type **`Preferences:
    Package Control Settings – User`** on the opened quick panel and press <kbd>Enter</kbd>
1. Then,
    find the following setting on your **`Package Control.sublime-settings`** file:
    ```js
    "channels":
    [
        "https://packagecontrol.io/channel_v3.json",
        "https://raw.githubusercontent.com/evandrocoan/StudioChannel/master/channel.json",
    ],
    ```
1. And,
    change it to the following, i.e.,
    put the **`https://raw.githubusercontent...`** line as first:
    ```js
    "channels":
    [
        "https://raw.githubusercontent.com/evandrocoan/StudioChannel/master/channel.json",
        "https://packagecontrol.io/channel_v3.json",
    ],
    ```
    * The **`https://raw.githubusercontent...`** line must to be added before the **`https://packagecontrol.io...`** one, otherwise,
      you will not install this forked version of the package,
      but the original available on the Package Control default channel **`https://packagecontrol.io...`**
    > [!WARNING]
    > Placing this custom channel before the default channel changes Package Control's resolution globally.
    > Packages from this channel with the same name will override versions from the default channel.
    >
    > You can review the channel contents here:
    > https://raw.githubusercontent.com/evandrocoan/StudioChannel/master/channel.json
1. Now,
    go to the menu **`Preferences -> Package Control`**
1. Type **`Install Package`** on the opened quick panel and press <kbd>Enter</kbd>
1. Then,
    search for **`Origami`** and press <kbd>Enter</kbd>

See also:

1. [ITE - Integrated Toolset Environment](https://github.com/evandrocoan/ITE)
1. [Package control docs](https://packagecontrol.io/docs/usage) for details.

