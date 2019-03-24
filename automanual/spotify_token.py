from getpass import getpass

from hyperlink import URL
import spotipy.util


USERNAME = ";-.-;"
CLIENT_ID = u"9c3971b106ea4e019c04967a0974b1af"
DASHBOARD = URL(scheme=u"https", host=u"beta.developer.spotify.com").child(
    u"dashboard", u"applications", CLIENT_ID,
)
PROMPT = "Client Secret (" + DASHBOARD.to_text().encode("ascii") + "): "

print spotipy.util.prompt_for_user_token(
    username=USERNAME,
    scope="user-library-read",
    redirect_uri="http://localhost:8080/",
    client_id=CLIENT_ID,
    client_secret=getpass(PROMPT),
)
