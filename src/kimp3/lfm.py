
import lastfm
from models import AudioTags

lastfm.init_lastfm()
net = lastfm.network

at = AudioTags(title="Актриса весна", artist="DDT", album="актриса весна")
lft = lastfm.LastFMTrack(at)

