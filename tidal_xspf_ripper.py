#!/usr/bin/env python3

import os
import time
import shutil
import subprocess
import logging
import xml.etree.ElementTree as ET
import sys

PLAYER = "strawberry"

TRACKS_DIR = "tracks"
COVERS_DIR = "covers"

EXPORT_WAIT = 5

track_count = 0
start_time = time.time()

logging.basicConfig(
    level=logging.INFO,
    format="\033[32m[%(levelname)s]\033[0m %(message)s"
)

log = logging.getLogger("ripper")


def ensure_dirs():
    os.makedirs(TRACKS_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)


def parse_xspf(path):

    tree = ET.parse(path)
    root = tree.getroot()

    ns = {"x": "http://xspf.org/ns/0/"}

    tracks = []

    for track in root.findall(".//x:track", ns):

        tracks.append({
            "location": track.findtext("x:location", "", ns),
            "title": track.findtext("x:title", "", ns),
            "creator": track.findtext("x:creator", "", ns),
            "album": track.findtext("x:album", "", ns),
            "tracknum": track.findtext("x:trackNum", "", ns),
        })

    return tracks


def generate_temp_xspf(track):

    path = "/tmp/ripper_track.xspf"

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<playlist version="1" xmlns="http://xspf.org/ns/0/">
 <trackList>
  <track>
   <location>{track["location"]}</location>
   <title>{track["title"]}</title>
   <creator>{track["creator"]}</creator>
   <album>{track["album"]}</album>
   <trackNum>{track["tracknum"]}</trackNum>
  </track>
 </trackList>
</playlist>
"""

    with open(path, "w") as f:
        f.write(content)

    return path


class AudacityPipe:

    def __init__(self):

        uid = os.getuid()

        self.to = f"/tmp/audacity_script_pipe.to.{uid}"
        self.from_ = f"/tmp/audacity_script_pipe.from.{uid}"

        if not os.path.exists(self.to):
            log.error("Audacity pipe not found")
            exit(1)

        log.info(f"Write pipe : {self.to}")
        log.info(f"Read pipe  : {self.from_}")

        self.tofile = open(self.to, "w")
        self.fromfile = open(self.from_, "rt")

    def send(self, cmd):
        self.tofile.write(cmd + "\n")
        self.tofile.flush()

    def read(self):

        result = ""

        while True:

            line = self.fromfile.readline()

            if line == "\n":
                break

            result += line

        return result

    def command(self, cmd):
        self.send(cmd)
        return self.read()


def sanitize(name):
    return name.replace(" ", "-").replace("/", "_")


def get_metadata():

    try:

        output = subprocess.check_output(
            [
                "playerctl",
                "--player",
                PLAYER,
                "metadata",
                "--format",
                "{{title}}|{{artist}}|{{album}}|{{mpris:artUrl}}"
            ],
            text=True
        ).strip()

    except:
        return {}

    parts = output.split("|")

    return {
        "title": parts[0],
        "artist": parts[1],
        "album": parts[2],
        "artUrl": parts[3],
    }


def wait_for_cover():

    log.info("Waiting DBus cover arrival")

    proc = subprocess.Popen(
        [
            "playerctl",
            "--player",
            PLAYER,
            "--follow",
            "metadata",
            "--format",
            "{{mpris:artUrl}}"
        ],
        stdout=subprocess.PIPE,
        text=True
    )

    for line in proc.stdout:

        url = line.strip()

        if url.startswith("file://"):
            proc.kill()
            return url.replace("file://", "")


def store_cover(path, meta):

    if not path:
        return None

    title = sanitize(meta.get("title", "cover"))

    ext = os.path.splitext(path)[1]

    dst = os.path.join(COVERS_DIR, title + ext)

    if not os.path.exists(dst):

        shutil.copy2(path, dst)
        log.info(f"Stored cover : {dst}")

    return dst


def write_tags(filepath, meta):

    subprocess.run([
        "metaflac",
        f"--set-tag=TITLE={meta.get('title','')}",
        f"--set-tag=ARTIST={meta.get('artist','')}",
        f"--set-tag=ALBUM={meta.get('album','')}",
        filepath
    ])


def embed_cover(filepath, cover):

    if not cover:
        return

    subprocess.run([
        "metaflac",
        f"--import-picture-from={cover}",
        filepath
    ])


def export_track(pipe, meta):

    global track_count

    track_count += 1

    title = sanitize(meta.get("title", "track"))
    filename = title + ".flac"
    path = os.path.join(TRACKS_DIR, filename)

    log.info("")
    log.info(f"========== TRACK {track_count} ==========")
    log.info(f"TITLE  : {meta.get('title','')}")
    log.info(f"ARTIST : {meta.get('artist','')}")
    log.info(f"ALBUM  : {meta.get('album','')}")
    log.info(f"EXPORT : {path}")

    pipe.command("Stop:")
    pipe.command("SelectAll:")
    pipe.command("MixAndRender:")

    pipe.command(
        f'Export2: Filename="{os.path.abspath(path)}" '
        "NumChannels=2 "
        "SampleRate=48000 "
        "BitDepth=24"
    )

    log.info("Waiting export completion")

    time.sleep(EXPORT_WAIT)

    if os.path.exists(path):

        write_tags(path, meta)

        embed_cover(path, meta.get("cover_path"))

    pipe.command("SelectAll:")
    pipe.command("RemoveTracks:")


def wait_track_end(initial_title):

    while True:

        meta = get_metadata()

        if meta.get("title") != initial_title:
            return

        time.sleep(1)


def main():

    if len(sys.argv) != 2:
        print("Usage: ripper.py playlist.xspf")
        exit(1)

    xspf = sys.argv[1]

    ensure_dirs()

    tracks = parse_xspf(xspf)

    log.info(f"Tracks found : {len(tracks)}")

    pipe = AudacityPipe()
    pipe.command("SelectAll:")
    pipe.command("RemoveTracks:")

    for i, track in enumerate(tracks, 1):

        log.info("")
        log.info(f"Opening track {i}/{len(tracks)} : {track['location']}")

        tmp = generate_temp_xspf(track)

        subprocess.run(["playerctl","--player",PLAYER,"open",tmp])

        time.sleep(20)

        subprocess.run(["playerctl","--player",PLAYER,"pause"])

        meta = get_metadata()

        cover_tmp = wait_for_cover()

        cover = store_cover(cover_tmp, meta)

        meta["cover_path"] = cover

        pipe.command("Record1stChoice:")

        time.sleep(1)

        subprocess.run(["playerctl","--player",PLAYER,"open",tmp])

        wait_track_end(meta.get("title"))

        export_track(pipe, meta)


if __name__ == "__main__":
    main()