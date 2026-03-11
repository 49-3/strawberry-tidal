"""
Tidal playlist to Strawberry .xspf converter using the Tidal API.
"""
import tidalapi
import pathlib
import sys
import xml.etree.ElementTree as ET


def authenticate():
    session = tidalapi.Session()
    login, future = session.login_oauth()

    print(f"Ouvre ce lien pour te connecter : https://{login.verification_uri_complete}")
    print(f"Code : {login.user_code}")

    input("Appuie sur Entrée après t'être connecté...")
    future.result()

    print(f"Connecté en tant que {session.user.first_name} {session.user.last_name}\n")
    return session


def fetch_playlist(session, playlist_id):
    playlist = session.playlist(playlist_id)
    tracks = playlist.tracks()
    return playlist, tracks


def build_xspf(playlist_name, tracks):
    ns = "http://xspf.org/ns/0/"
    root = ET.Element("playlist", version="1", xmlns=ns)
    track_list = ET.SubElement(root, "trackList")

    for i, track in enumerate(tracks, 1):

        t = ET.SubElement(track_list, "track")

        loc = ET.SubElement(t, "location")
        loc.text = f"tidal:{track.id}"   # ← FIX ICI

        title = ET.SubElement(t, "title")
        title.text = track.name

        creator = ET.SubElement(t, "creator")
        creator.text = ", ".join(a.name for a in track.artists)

        album = ET.SubElement(t, "album")
        album.text = track.album.name if track.album else ""

        num = ET.SubElement(t, "trackNum")
        num.text = str(i)

    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def extract_playlist_id(url):
    url = url.strip().rstrip("/")

    for prefix in ("/playlist/", "/browse/playlist/"):
        if prefix in url:
            return url.split(prefix)[1].split("?")[0].split("/")[0]

    if len(url) == 36 and url.count("-") == 4:
        return url

    return url


def main():

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        print("Convertisseur de playlists Tidal vers Strawberry (.xspf)")
        url = input("Entre l'URL de ta playlist Tidal : ")

    playlist_id = extract_playlist_id(url)
    print(f"Playlist ID : {playlist_id}\n")

    session = authenticate()
    playlist, tracks = fetch_playlist(session, playlist_id)

    print(f"Playlist : {playlist.name}")
    print(f"Nombre de titres : {len(tracks)}\n")

    for i, t in enumerate(tracks, 1):
        artists = ", ".join(a.name for a in t.artists)
        print(f"{i:3d}. {artists} - {t.name}")

    xml = build_xspf(playlist.name, tracks)

    filename = f"{playlist.name.replace(' ', '-')}.xspf"
    pathlib.Path(filename).write_text(xml)

    print(f"\nExporté dans '{filename}' !")
    print("Importe la playlist dans Strawberry.")


if __name__ == "__main__":
    main()