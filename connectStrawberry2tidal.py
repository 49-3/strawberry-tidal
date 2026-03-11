import tidalapi
import configparser
import time
import os
import subprocess

CONF = os.path.expanduser("~/.config/strawberry/strawberry.conf")

# 1) Auth Tidal via device flow
session = tidalapi.Session()
login, future = session.login_oauth()
print(f"Va sur: https://{login.verification_uri_complete}")
print(f"Code: {login.user_code}")
input("Appuie sur Entrée après t'être connecté...")
future.result()

print(f"\n--- Tokens obtenus ---")
print(f"Token type: {session.token_type}")
print(f"User ID: {session.user.id}")
print(f"Country: {session.country_code}")
print(f"Access token: {session.access_token}")
print(f"Refresh token: {session.refresh_token}")
print(f"Expiry: {session.expiry_time}")

# 2) Fermer Strawberry
print("\nFermeture de Strawberry...")
subprocess.run(["killall", "strawberry"], capture_output=True)
time.sleep(2)

# 3) Injecter les tokens dans la config Strawberry
config = configparser.RawConfigParser()
config.optionxform = str  # garder la casse des clés
config.read(CONF)

if "Tidal" not in config:
    config.add_section("Tidal")

config.set("Tidal", "enabled", "true")
config.set("Tidal", "access_token", session.access_token)
config.set("Tidal", "refresh_token", session.refresh_token)
config.set("Tidal", "token_type", session.token_type or "Bearer")
config.set("Tidal", "user_id", str(session.user.id))
config.set("Tidal", "country_code", session.country_code)
config.set("Tidal", "login_time", str(int(time.time())))
config.set("Tidal", "expires_in", str(int(session.expiry_time.timestamp() - time.time())))

# Supprimer les anciennes clés invalides
for old_key in ["token_expiry", "session_id"]:
    if config.has_option("Tidal", old_key):
        config.remove_option("Tidal", old_key)

with open(CONF, "w") as f:
    config.write(f)

print(f"\nConfig écrite dans {CONF}")
print("Relance Strawberry maintenant!")