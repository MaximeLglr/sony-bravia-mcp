from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bravia_client import BraviaClient  # noqa: E402
from bravia_client.config import BraviaConfig  # noqa: E402

INPUTS = [
    {"uri": "extInput:cec?port=1&type=player&logicalAddr=4", "title": "Apple TV",
     "connection": True, "label": "", "icon": "meta:playbackdevice"},
    {"uri": "extInput:cec?port=4&type=player&logicalAddr=8", "title": "PlayStation 5",
     "connection": True, "label": "", "icon": "meta:playbackdevice"},
    {"uri": "extInput:hdmi?port=1", "title": "HDMI 1", "connection": True,
     "label": "", "icon": "meta:hdmi"},
    {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "connection": False,
     "label": "", "icon": "meta:hdmi"},
    {"uri": "extInput:hdmi?port=3", "title": "HDMI 3 (eARC/ARC)", "connection": False,
     "label": "", "icon": "meta:hdmi"},
    {"uri": "extInput:hdmi?port=4", "title": "HDMI 4", "connection": False,
     "label": "", "icon": "meta:hdmi"},
]

APPS = [
    {"title": "Param\u00e8tres", "uri": "com.sony.dtv.com.android.tv.settings.com.android.tv.settings.MainSettings"},
    {"title": "Play\u00a0Store", "uri": "com.sony.dtv.com.android.vending.com.google.android.finsky.tvmainactivity.TvMainActivity"},
    {"title": "YouTube", "uri": "com.sony.dtv.com.google.android.youtube.tv.com.google.android.apps.youtube.tv.activity.ShellActivity"},
    {"title": "YouTube Music", "uri": "com.sony.dtv.com.google.android.youtube.tvmusic.com.google.android.apps.youtube.tvmusic.activity.MainActivity"},
    {"title": "TV", "uri": "com.sony.dtv.com.sony.dtv.tvlin.com.sony.dtv.tvlin.view.MainActivity"},
    {"title": "Netflix", "uri": "com.sony.dtv.com.netflix.ninja.com.netflix.ninja.MainActivity"},
    {"title": "D\u00e9cor d&apos;int\u00e9rieur", "uri": "com.sony.dtv.com.sony.dtv.livingfit.com.sony.dtv.livingfit.MainActivity"},
    {"title": "Contr\u00f4le TV avec des enceintes intelligentes", "uri": "com.sony.dtv.com.sony.dtv.seeds.iot.x.InitialActivity"},
    {"title": "Disney+", "uri": "com.sony.dtv.com.disney.disneyplus.com.bamtechmedia.dominguez.main.MainActivity"},
]


class FakeTV:
    def __init__(self):
        self.power = "active"
        self.playing = "extInput:cec?port=1&type=player&logicalAddr=4"
        self.volume = 22
        self.muted = False
        self.calls: list[tuple[str, str, list]] = []
        self.psk = "secret"
        self.fail_times = 0
        self.last_app = ""

        self.handler = self._handler

    def _handler(self, request: httpx.Request) -> httpx.Response:
        service = request.url.path.split("/")[-1]
        body = json.loads(request.content)
        method, params = body["method"], body.get("params", [])
        self.calls.append((service, method, params))

        if self.fail_times > 0:
            self.fail_times -= 1
            return httpx.Response(503, json={"error": [503, "unavailable"]})

        if request.headers.get("X-Auth-PSK") not in (None, self.psk):
            return httpx.Response(403)

        def ok(result):
            return httpx.Response(200, json={"result": result, "id": body["id"]})

        if method == "getPowerStatus":
            return ok([{"status": self.power}])
        if method == "setPowerStatus":
            self.power = "active" if params[0]["status"] else "standby"
            return ok([])
        if method == "getSystemInformation":
            return ok([{"product": "TV", "model": "K-55XR8M2", "area": "FRA"}])
        if method == "getCurrentExternalInputsStatus":
            return ok([INPUTS])
        if method == "getPlayingContentInfo":
            if self.power != "active":
                return httpx.Response(200, json={"error": [40005, "Display Is Turned off"], "id": body["id"]})
            title = next((i["title"] for i in INPUTS if i["uri"] == self.playing), "?")
            return ok([{"uri": self.playing, "title": title, "source": "extInput:cec"}])
        if method == "setPlayContent":
            self.playing = params[0]["uri"]
            return ok([])
        if method == "getApplicationList":
            return ok([APPS])
        if method == "setActiveApp":
            self.last_app = params[0]["uri"]
            return ok([])
        if method == "getVolumeInformation":
            return ok([[{"target": "speaker", "volume": self.volume, "mute": self.muted,
                         "maxVolume": 100, "minVolume": 0}]])
        if method == "setAudioVolume":
            v = params[0]["volume"]
            self.volume = self.volume + int(v) if v[0] in "+-" else int(v)
            return ok([])
        if method == "setAudioMute":
            self.muted = params[0]["status"]
            return ok([])

        return httpx.Response(200, json={"error": [12, "No Such Method"], "id": body["id"]})


def make_client(tv: FakeTV, **config_overrides) -> BraviaClient:
    config = BraviaConfig(
        host="fake.local",
        psk=tv.psk,
        mac="EE:B2:EB:B7:99:A6",
        _env_file=None,
        **config_overrides,
    )
    return BraviaClient(config, handler=httpx.MockTransport(tv.handler))


@pytest.fixture
def tv() -> FakeTV:
    return FakeTV()


@pytest.fixture
def client(tv: FakeTV) -> BraviaClient:
    return make_client(tv)
