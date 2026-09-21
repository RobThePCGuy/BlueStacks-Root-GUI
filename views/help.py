"""The "?" help: one short page of help for whichever page is on screen.

Explanations live here and in tooltips, not printed across the window. The
window itself carries only state, prompts and warnings, so it stays readable;
anyone who wants the why presses "?" (or F1 / Cmd+?) on the page they are on.

Windows BlueStacks and BlueStacks Air get different text where they genuinely
differ (Air has one root method, no engine patch and no Modules page), so the
help never describes a button that is not on screen.
"""
from __future__ import annotations

import os
import tempfile

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

import constants
from views.nav_rail import DASHBOARD, INSTANCES, MODULES, PRIVACY

GUIDE_URL = "https://github.com/RobThePCGuy/BlueStacks-Root-GUI#readme"
LOG_PATH = os.path.join(tempfile.gettempdir(), "BlueStacksRootGUI.log")

_TITLES = {
    DASHBOARD: "Dashboard",
    INSTANCES: "Instances",
    MODULES: "Modules",
    PRIVACY: "Privacy",
}

_DASHBOARD_WINDOWS = """
<p>Where BlueStacks was found, and how many instances are rooted.</p>
<h3>Patch BlueStacks Engine</h3>
<p>Current BlueStacks (5.22.150 and newer) checks itself for tampering and
refuses to boot a rooted instance. This button patches that check out. Do it
once per install, before rooting. BlueStacks is closed first, and the original
files are backed up. Once patched, the same button reads <b>Engine patched
(click to Undo)</b> and puts them back.</p>
<h3>"An auto-update undid your engine patch"</h3>
<p>A BlueStacks update replaced the patched files. Click <b>Re-patch now</b>.
To stop it recurring, turn off BlueStacks' updater (see the full guide).</p>
"""

_DASHBOARD_AIR = """
<p>Where BlueStacks Air was found, and whether it is rooted.</p>
<p>Air has no engine patch to apply. Go to <b>Instances</b> to root it.</p>
"""

_INSTANCES_WINDOWS = """
<p>Tick an instance to act on it. Root and R/W work on every ticked instance;
the rest need exactly one.</p>
<h3>Two ways to root, pick one</h3>
<ul>
<li><b>Native Root</b>: BlueStacks' own su. Quick and reversible. Enough for
root apps and root checkers. No modules.</li>
<li><b>Manager Root</b>: Magisk. Adds modules, Zygisk and LSPosed. Switches
Native Root off for you.</li>
</ul>
<p>Never run both: they fight over su. The Root column says which one each
instance uses, and <b>Native + Manager</b> means switch Native Root off.</p>
<h3>Adding modules</h3>
<p>With Manager Root in: <b>ReZygisk</b> first, then <b>LSPosed</b>, then
<b>Restart</b> once to activate them.</p>
<h3>Other buttons</h3>
<ul>
<li><b>Launch</b> starts the ticked instance. <b>Restart</b> closes BlueStacks
and starts it again.</li>
<li><b>Toggle R/W</b> makes the instance's system disk writable, which some
manual changes need. Leave it read-only otherwise.</li>
</ul>
<p>Close the instance before changing root; the tool closes BlueStacks for you
when it has to.</p>
"""

_INSTANCES_AIR = """
<p>BlueStacks Air ships no su, so rooting adds one to the Android system
image. Every Air instance shares that one image, so root covers all of them.</p>
<h3>To root</h3>
<ol>
<li>Tick your instance and click <b>Root (all instances)</b>. BlueStacks is
closed for you.</li>
<li><b>First time only:</b> macOS blocks the change and this tool opens
<b>System Settings &gt; Privacy &amp; Security &gt; App Management</b>. Switch
<b>BlueStacksRootGUI</b> on, choose <b>Quit &amp; Reopen</b>, and click Root
again. After updating this tool you do this once more.</li>
<li>Wait about a minute, then start BlueStacks. Root apps and root checkers now
see su.</li>
</ol>
<h3>To undo</h3>
<p>Click <b>Remove Root</b>. The original image is put back exactly as it was.</p>
<h3>Good to know</h3>
<ul>
<li>A BlueStacks update replaces the image and removes root. Click Root again.</li>
<li>While rooted, BlueStacks' Apple signature no longer checks out. BlueStacks
still runs normally, and undoing repairs it.</li>
<li>You never need your Mac password for this. If macOS says it blocked the
change, it is the App Management switch above.</li>
</ul>
"""

_MODULES = """
<p>Installs a Magisk module .zip into a running instance that has
<b>Manager Root</b>.</p>
<ol>
<li>Start the instance (Instances &gt; Launch). It appears in the list.</li>
<li>Pick it, click <b>Browse...</b> and choose the module .zip.</li>
<li>Click <b>Push and flash module</b>, then close and reopen the instance.</li>
</ol>
<p>This exists because BlueStacks' own file picker hands Magisk a path it cannot
open. If the tool cannot reach the instance, it leaves the .zip in the
instance's Download folder so you can flash it from the Magisk app.</p>
"""

_PRIVACY = """
<h3>BlueStacks ads &amp; telemetry</h3>
<p>Turns off BlueStacks' own ads, promos and stats uploads, for every instance.
Every original setting is recorded, so <b>Restore BlueStacks defaults</b> puts
them back exactly.</p>
<p>BlueStacks sometimes turns a few back on. <b>Lock config file</b> stops that,
but also stops BlueStacks saving its own settings, so unlock it before changing
anything in BlueStacks.</p>
<h3>In-guest tracker block</h3>
<p>Blocks known tracker domains for the apps running <i>inside</i> Android. It
does not affect BlueStacks' own ads (that is the section above). Pick an
instance and click <b>Block in-guest trackers</b>; <b>Remove block</b> undoes
it. BlueStacks is closed first.</p>
"""

_PRIVACY_WINDOWS_NOTE = """
<p>The tracker block covers every instance on the same Android version, and
needs the engine patch (Dashboard).</p>
"""

_PRIVACY_AIR_NOTE = """
<p>On Air the tracker block covers every instance, like root does, and needs the
same App Management switch the first time.</p>
"""


def help_html(key: str, air: bool) -> str:
    """The help body for one page, for Windows BlueStacks or Air."""
    if key == DASHBOARD:
        body = _DASHBOARD_AIR if air else _DASHBOARD_WINDOWS
    elif key == INSTANCES:
        body = _INSTANCES_AIR if air else _INSTANCES_WINDOWS
    elif key == MODULES:
        body = _MODULES
    elif key == PRIVACY:
        body = _PRIVACY + (_PRIVACY_AIR_NOTE if air else _PRIVACY_WINDOWS_NOTE)
    else:
        body = ""
    footer = (
        "<hr><p>Something went wrong? The log is at <code>%s</code>.<br>"
        '<a href="%s">Full guide on GitHub</a></p>' % (LOG_PATH, GUIDE_URL))
    return "<h2>%s</h2>%s%s" % (_TITLES.get(key, "Help"), body, footer)


class HelpDialog(QDialog):
    """Help for the page on screen. Modeless, so it can stay open beside it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("%s Help" % constants.APP_NAME)
        self.resize(560, 560)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.document().setDocumentMargin(10)
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def show_page(self, key: str, air: bool) -> None:
        self.browser.setHtml(help_html(key, air))
