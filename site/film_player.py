"""An opt-in player for a private local site preview."""
import hashlib
import shutil
from pathlib import Path
from string import Template
from typing import Optional, Tuple

MEDIA_DIR = "private-film"
V6_PRIMARY = "Morning-departures.mp4"
V6_REDUCED = "Morning-departures-reduced-motion.mp4"
# The illustrated dispatch record was checked against both of these cuts.
DISPATCH_CUTS = {
    "film.mp4": "e055a9a60378962e7dc96d902e8784ac2617a31b30ef001db29975e86830773d",
    "reduced-motion.mp4": "542c604121dfde71d392594b8cf0dd00b218dced823e633fba5d8c369ee68f0b",
}
FILM_INVITATION = "AI operating system demo"
FILM_SUBTITLE = "A transit operator checks the morning bus schedule"
FILM_CONTEXT = "Example of an agentic operating system"


def preview_files(directory: Optional[Path], out: Path, release: bool) -> Tuple[Path, ...]:
    """Resolve the exact preview inputs before the caller replaces its output tree."""
    if directory is None:
        return ()
    if release:
        raise SystemExit("A release cannot include a private film preview.")
    directory = Path(directory).expanduser()
    if directory.is_symlink():
        raise SystemExit("Use the film directory itself, not a symbolic link.")
    folder = directory.resolve()
    output = Path(out).resolve()
    if folder == output or output in folder.parents or folder in output.parents:
        raise SystemExit("The private film inputs and the site output must be separate directories.")
    if not folder.is_dir():
        raise SystemExit("The private film preview directory does not exist.")
    names = {entry.name for entry in folder.iterdir()}
    primary = names.intersection({"film.mp4", V6_PRIMARY})
    posters = names.intersection({"poster.webp", "poster.jpg", "poster.png"})
    if len(primary) != 1 or len(posters) != 1:
        raise SystemExit("A private preview needs one primary film and one poster.webp, poster.jpg or poster.png.")
    movie = primary.pop()
    selected = [folder / movie, folder / posters.pop()]
    if movie == V6_PRIMARY:
        selected.append(folder / V6_REDUCED)
    if "captions.vtt" in names:
        selected.append(folder / "captions.vtt")
    for path in selected:
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise SystemExit("Use a non-empty regular file for each private preview asset.")
    return tuple(selected)


def opening_link(files: Tuple[Path, ...]) -> str:
    if not any(path.name == V6_PRIMARY for path in files):
        return ""
    return (f'<a class="film-entry" href="#field-film" aria-label="{FILM_INVITATION}. '
            f'{FILM_SUBTITLE}. Play with sound, 1 minute 40 seconds.">'
            '<span class="film-entry-ring" aria-hidden="true">▶</span>'
            f'<span class="film-entry-lines"><span class="film-entry-title">{FILM_INVITATION}</span>'
            f'<span class="film-premise">{FILM_SUBTITLE} <span aria-hidden="true">·</span> '
            '<span class="film-duration">1:40</span></span></span></a>')


def copy_preview(files: Tuple[Path, ...], out: Path) -> str:
    """Copy the selected assets and return only the optional homepage fragment."""
    if not files:
        return ""
    target = Path(out) / MEDIA_DIR
    target.mkdir()
    public_names = {V6_PRIMARY: "film.mp4", V6_REDUCED: "reduced-motion.mp4"}
    for source in files:
        shutil.copy2(source, target / public_names.get(source.name, source.name))
    poster = files[1].name
    names = {source.name for source in files}
    reduced = ('<source media="(prefers-reduced-motion: reduce)" src="private-film/reduced-motion.mp4" type="video/mp4">\n'
               if V6_REDUCED in names else "")
    track = ('<track kind="captions" srclang="en" label="English" src="private-film/captions.vtt">'
             if "captions.vtt" in names else "")
    transit_film = V6_PRIMARY in names
    title = "A transit operator checks the morning bus report" if transit_film else "Film preview"
    context = f'<p class="film-context">{FILM_CONTEXT}</p>' if transit_film else ""
    caption = ('<figcaption>Dispatch is waiting for your report. Which buses would you count, '
               'and how would the next shift know why? '
               '<a class="film-download" href="#start" hidden>Download ThesisAnalysisOS</a></figcaption>'
               if transit_film else "")
    record = ""
    if transit_film and all(hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
                            for name, digest in DISPATCH_CUTS.items()):
        record = Path(__file__).with_name("film_record.html").read_text(encoding="utf-8")
    template = Path(__file__).with_name("film_player.html").read_text(encoding="utf-8")
    return Template(template).substitute(poster=poster, reduced=reduced, track=track, title=title, context=context,
                                         caption=caption, record=record)
