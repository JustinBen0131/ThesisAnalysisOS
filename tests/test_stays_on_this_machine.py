"""The program talks to nothing but the machine it runs on.

The README says an answer needs "no model call, no network, no account". This test keeps that true as the code grows:
only three modules may open a socket at all (the local panel, the welcome page and one check fixture), every address they name is this
machine, and the one web address in the program is the clone command it prints for a person, never opened.
A new module that needs the network fails here first, so the claim is changed on purpose or not at all.
"""
import re
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "taos_core"
NETWORK = re.compile(
    r"^\s*(?:import|from)\s+(socket|socketserver|ssl|urllib\.request|http\.client|http\.server|ftplib|smtplib|"
    r"poplib|imaplib|telnetlib|xmlrpc|asyncio|requests|httpx|aiohttp|websockets?)\b", re.M)
MAY_OPEN_A_SOCKET = {"gates.py", "panel.py", "welcome.py"}
THIS_MACHINE = ("127.0.0.1", "localhost")
ADDRESS = re.compile(r"""["'](https?://[^"'\s{]*)""")
# the ("host", port) a socket binds or connects to: the first argument of a call, so a table of pairs is not mistaken
HOST_PAIR = re.compile(r"""\w\(\s*\(\s*["']([^"']*)["']\s*,""")


def sources():
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(CORE.rglob("*.py"))}


class StaysOnThisMachine(unittest.TestCase):
    def test_only_the_panel_the_welcome_page_and_one_fixture_can_open_a_socket(self):
        able = {name for name, text in sources().items() if NETWORK.search(text)}
        self.assertEqual(able, MAY_OPEN_A_SOCKET,
                         "a module gained or lost network code; the README's 'no network' rests on this list")

    def test_every_address_those_modules_name_is_this_machine(self):
        for name, text in sources().items():
            if name not in MAY_OPEN_A_SOCKET:
                continue
            for host in HOST_PAIR.findall(text):
                self.assertIn(host, THIS_MACHINE, "{0} binds or connects to {1!r}".format(name, host))
            for address in ADDRESS.findall(text):
                rest = address.split("://", 1)[1]
                self.assertTrue(rest.startswith(THIS_MACHINE), "{0} names {1}".format(name, address))
            self.assertGreater(len(HOST_PAIR.findall(text)) + len(ADDRESS.findall(text)), 0,
                               "{0} has network code but this test found no address to judge".format(name))

    def test_the_only_web_address_elsewhere_is_printed_for_a_person(self):
        named = {}
        for name, text in sources().items():
            if name in MAY_OPEN_A_SOCKET:
                continue
            outside = [a for a in ADDRESS.findall(text) if not a.split("://", 1)[1].startswith(THIS_MACHINE)]
            if outside:
                named[name] = sorted(set(outside))
        self.assertEqual(named, {"use.py": ["https://github.com/JustinBen0131/ThesisAnalysisOS.git"]},
                         "a web address appeared in a module; say what opens it, or that nothing does")
        self.assertIsNone(NETWORK.search(sources()["use.py"]), "use.py prints the clone command and must not fetch it")


if __name__ == "__main__":
    unittest.main()
