"""The homepage demonstration and opt-in previews of other cuts."""
import hashlib
import shutil
from pathlib import Path
from string import Template
from typing import Optional, Tuple

PUBLIC_MEDIA_DIR = "films/morning-departures"
PUBLIC_INPUT = Path(__file__).resolve().parent / "media" / "morning-departures"
V6_PRIMARY = "Morning-departures.mp4"
V6_REDUCED = "Morning-departures-reduced-motion.mp4"
# The illustrated dispatch record was checked against both of these cuts.
DISPATCH_CUTS = {
    "film.mp4": "e055a9a60378962e7dc96d902e8784ac2617a31b30ef001db29975e86830773d",
    "reduced-motion.mp4": "542c604121dfde71d392594b8cf0dd00b218dced823e633fba5d8c369ee68f0b",
}
PUBLIC_DIGESTS = {**DISPATCH_CUTS,
                  "poster.jpg": "d204522f43886f41c24f18af8bb44eb1380bfdaad01b6c65ff45a041d8ffe55d",
                  "captions.vtt": "82c775539a80adfeb94082a7920b46b6be088b86d236fa986a212bb71142820f"}
FILM_INVITATION = "Watch it work on a morning bus report."
FILM_SUBTITLE = "A transit operator checks the morning bus schedule"
FILM_CONTEXT = "An everyday job, start to finish. 1 min 40, with sound."


def film_files(directory: Optional[Path], out: Path, release: bool) -> Tuple[Path, ...]:
    """Use the published cut by default and allow a local preview to supply its own files."""
    if directory is not None and release:
        raise SystemExit("A release cannot include a private film preview.")
    bundled = directory is None
    directory = PUBLIC_INPUT if bundled else Path(directory).expanduser()
    if directory.is_symlink():
        raise SystemExit("Use the film directory itself, not a symbolic link.")
    folder = directory.resolve()
    output = Path(out).resolve()
    if folder == output or output in folder.parents or folder in output.parents:
        raise SystemExit("The film inputs and the site output must be separate directories.")
    if not folder.is_dir():
        raise SystemExit("The film directory does not exist.")
    if bundled:
        return (folder / V6_PRIMARY, folder / "poster.jpg", folder / V6_REDUCED, folder / "captions.vtt")
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


def render_player(files: Tuple[Path, ...], out: Path, media_dir: str) -> str:
    """Copy the selected film and render the homepage player using site-relative URLs."""
    target = Path(out) / media_dir
    target.mkdir(parents=True)
    public_names = {V6_PRIMARY: "film.mp4", V6_REDUCED: "reduced-motion.mp4"}
    for source in files:
        shutil.copy2(source, target / public_names.get(source.name, source.name))
    poster = files[1].name
    names = {source.name for source in files}
    reduced = (f'<source media="(prefers-reduced-motion: reduce)" src="{media_dir}/reduced-motion.mp4" type="video/mp4">\n'
               if V6_REDUCED in names else "")
    track = (f'<track kind="captions" srclang="en" label="English" src="{media_dir}/captions.vtt">'
             if "captions.vtt" in names else "")
    transit_film = V6_PRIMARY in names
    title = FILM_INVITATION if transit_film else "Film preview"
    context = f'<p class="film-context">{FILM_CONTEXT}</p>' if transit_film else ""
    caption = ('<figcaption>Dispatch is waiting for your report. Which buses would you count, '
               'and how would the next shift know why? '
               '<a class="film-workflow" href="workflows/transit/">Pick up the next shift’s report</a> '
               '<a class="film-download" href="#run" hidden>Download ThesisAnalysisOS</a></figcaption>'
               if transit_film else "")
    record = ""
    if transit_film and all(hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
                            for name, digest in DISPATCH_CUTS.items()):
        record = Path(__file__).with_name("film_record.html").read_text(encoding="utf-8")
    template = Path(__file__).with_name("film_player.html").read_text(encoding="utf-8")
    return Template(template).substitute(media_dir=media_dir, poster=poster, reduced=reduced, track=track,
                                         title=title, context=context, caption=caption, record=record)
