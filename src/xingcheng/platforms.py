"""Platform-specific native operations; calendar and OCR code stay portable."""

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def worker_command():
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "xingcheng.desktop_worker"]
    name = "calisift-worker.exe" if sys.platform == "win32" else "calisift-worker"
    return [str(Path(sys.executable).parent / name)]


def open_folder(path):
    if os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(
            ["open" if sys.platform == "darwin" else "xdg-open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def allowed_origin(value):
    from .assets import AssetServer

    url = urlsplit(str(value))
    return any(
        url.scheme == "http" and url.netloc == f"127.0.0.1:{s.port}"
        for s in AssetServer.instances
        if s.running
    )


def protect_cocoa(window):
    """Keep the renderer's delegate behavior, restricting top-level navigation."""
    from webview.platforms.cocoa import BrowserView
    from PyObjCTools import AppHelper
    import WebKit

    def install():
        browser = BrowserView.instances[window.uid]
        original = browser.webview.navigationDelegate()

        class CaliSiftNavigationDelegate(type(original)):
            def webView_decidePolicyForNavigationAction_decisionHandler_(
                self, view, action, handler
            ):
                if not allowed_origin(action.request().URL().absoluteString()):
                    handler(WebKit.WKNavigationActionPolicyCancel)
                    return
                original.webView_decidePolicyForNavigationAction_decisionHandler_(
                    view, action, handler
                )

        delegate = CaliSiftNavigationDelegate.alloc().init()
        browser.webview.setNavigationDelegate_(delegate)
        browser._calisift_delegate = delegate

    AppHelper.callAfter(install)


def copy_text(window, text):
    if sys.platform == "darwin":
        from AppKit import NSPasteboard, NSPasteboardTypeString
        from PyObjCTools import AppHelper

        def copy():
            board = NSPasteboard.generalPasteboard()
            board.clearContents()
            board.setString_forType_(text, NSPasteboardTypeString)

        AppHelper.callAfter(copy)
    elif os.name == "nt":
        from System import Action
        from System.Windows.Forms import Clipboard

        window.native.Invoke(Action(lambda: Clipboard.SetText(text)))
    else:
        raise ValueError(
            "此平台尚未提供原生剪贴板支持，可使用 calisift doctor 获取诊断"
        )
