"""Copy a command or prompt, with selectable text when JavaScript is unavailable."""

from html import escape as esc


def copy_block(identifier: str, value: str, label: str) -> str:
    return f"""<div class="command-block"><pre class="shell"><code id="{esc(identifier)}">{esc(value)}</code></pre>
<button type="button" class="copy-commands" aria-controls="{esc(identifier)}" aria-label="{esc(label)}" title="{esc(label)}" hidden>
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
<g class="copy-squares"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M15.5 5V4.8A1.8 1.8 0 0 0 13.7 3H5a2 2 0 0 0-2 2v8.7a1.8 1.8 0 0 0 1.8 1.8H5"/></g>
<path class="copy-check" d="m5 12 4.4 4.4L19 7"/></svg></button>
<span class="copy-status" role="status" aria-live="polite"></span></div>"""
