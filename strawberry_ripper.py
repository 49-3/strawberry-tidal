#!/usr/bin/env python3

import os
import time
import shutil
import subprocess
import logging

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

log = logging.getLogger("recorder")


def ensure_dirs():
    os.makedirs(TRACKS_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)


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
        "title": parts[0] if len(parts) > 0 else "",
        "artist": parts[1] if len(parts) > 1 else "",
        "album": parts[2] if len(parts) > 2 else "",
        "artUrl": parts[3] if len(parts) > 3 else "",
    }


def store_cover(meta):

    arturl = meta.get("artUrl", "")

    if not arturl.startswith("file://"):
        return None

    src = arturl.replace("file://", "")

    if not os.path.exists(src):
        return None

    title = sanitize(meta.get("title", "cover"))

    ext = os.path.splitext(src)[1]

    dst = os.path.join(COVERS_DIR, title + ext)

    if not os.path.exists(dst):

        shutil.copy2(src, dst)
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

    if not cover or not os.path.exists(cover):
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

        cover = meta.get("cover_path")

        embed_cover(path, cover)

        if cover:
            log.info(f"COVER  : {cover}")

    log.info("=================================")

    pipe.command("SelectAll:")
    pipe.command("RemoveTracks:")


def print_summary():

    elapsed = int(time.time() - start_time)

    minutes = elapsed // 60
    seconds = elapsed % 60

    log.info("")
    log.info("========== SESSION SUMMARY ==========")
    log.info(f"Tracks exported : {track_count}")
    log.info(f"Elapsed time    : {minutes:02}:{seconds:02}")
    log.info("=====================================")


def main():

    ensure_dirs()

    log.info("========== Strawberry Recorder ==========")
    log.info(f"Tracks dir : {TRACKS_DIR}")
    log.info(f"Covers dir : {COVERS_DIR}")
    log.info("=========================================")

    input("Press Enter to start")

    pipe = AudacityPipe()

    pipe.command("SetPreference: Name=/AudioIO/RecordChannels Value=2")

    pipe.command("SelectAll:")
    pipe.command("RemoveTracks:")

    pipe.command("Record1stChoice:")

    subprocess.run(["playerctl", "--player", PLAYER, "play"])

    time.sleep(2)

    meta = get_metadata()
    cover = store_cover(meta)
    meta["cover_path"] = cover

    previous_meta = meta
    previous_title = meta.get("title", "")

    log.info(f"Title  : {meta.get('title','')}")
    log.info(f"Artist : {meta.get('artist','')}")
    log.info(f"Album  : {meta.get('album','')}")
    log.info("Listening for track changes")

    proc = subprocess.Popen(
        [
            "playerctl",
            "--player",
            PLAYER,
            "--follow",
            "metadata",
            "--format",
            "{{title}}"
        ],
        stdout=subprocess.PIPE,
        text=True
    )

    try:

        for line in proc.stdout:

            title = line.strip()

            if not title:
                continue

            if title != previous_title:

                subprocess.run(["playerctl", "--player", PLAYER, "pause"])

                export_track(pipe, previous_meta)

                meta = get_metadata()
                cover = store_cover(meta)
                meta["cover_path"] = cover

                previous_title = title
                previous_meta = meta

                pipe.command("Record1stChoice:")

                time.sleep(1)

                subprocess.run(["playerctl", "--player", PLAYER, "play"])

    except KeyboardInterrupt:

        print_summary()


if __name__ == "__main__":
    main()