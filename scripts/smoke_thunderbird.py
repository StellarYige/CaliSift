"""Exercise a real Thunderbird import using an isolated profile and its own importer.

Pass a Thunderbird executable. No mail account, install, or third-party Python module
is required. The native file picker and delivery of alarm notifications are not tested.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
import time
from xingcheng.application import Application


class Marionette:
    def __init__(self, port):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.socket.settimeout(40)
        self.index = 0
        self.read()
        self.send("WebDriver:NewSession", {})
        self.send("Marionette:SetContext", {"value": "chrome"})

    def read(self):
        size = b""
        while not size.endswith(b":"):
            piece = self.socket.recv(1)
            if not piece:
                raise ConnectionError("Thunderbird disconnected")
            size += piece
        data = b""
        while len(data) < int(size[:-1]):
            piece = self.socket.recv(int(size[:-1]) - len(data))
            if not piece:
                raise ConnectionError("Thunderbird disconnected")
            data += piece
        return json.loads(data)

    def send(self, method, params):
        self.index += 1
        data = json.dumps([0, self.index, method, params]).encode()
        self.socket.sendall(str(len(data)).encode() + b":" + data)
        result = self.read()
        if result[2]:
            raise RuntimeError(result[2])
        return result[3]

    def script(self, script, args=(), asynchronous=False):
        return self.send(
            (
                "WebDriver:ExecuteAsyncScript"
                if asynchronous
                else "WebDriver:ExecuteScript"
            ),
            dict(
                script=script,
                args=list(args),
                newSandbox=True,
                sandbox="default",
                line=1,
                filename="calisift-calendar-verification",
            ),
        )["value"]


IMPORT_SCRIPT = """
const done=arguments[arguments.length-1],paths=arguments[0];
(async()=>{
 const w=Services.wm.getMostRecentWindow('mail:3pane');
 for(const other of Services.wm.getEnumerator(null)){
   if(other.location.href.includes('systemIntegrationDialog')) other.close();
 }
 w.document.getElementById('tabmail').openTab('calendar');
 const cal=ChromeUtils.importESModule('resource:///modules/calendar/calUtils.sys.mjs').cal;
 function emptyCalendar(){
   const c=cal.manager.createCalendar('storage',Services.io.newURI('moz-storage-calendar://'));
   c.name='CaliSift test';cal.manager.registerCalendar(c);return c;
 }
 let calendar=emptyCalendar(),outcomes=[];
 for(let i=0;i<paths.length;i++){
   if(i===4) calendar=emptyCalendar();
   const file=Cc['@mozilla.org/file/local;1'].createInstance(Ci.nsIFile);file.initWithPath(paths[i]);
   const items=w.getItemsFromIcsFile(file),error_messages=[];let duplicates=0;
   await w.putItemsIntoCal(calendar,items,{
     onDuplicate(){duplicates++},onError(item,error){error_messages.push(String(error));}
   });
   const stored=await calendar.getItemsAsArray(Ci.calICalendar.ITEM_FILTER_TYPE_EVENT,0,null,null);
   outcomes.push({input_count:items.length,duplicates,error_messages,count:stored.length,
     events:stored.map(e=>({id:e.id,title:e.title,start:e.startDate.icalString,end:e.endDate?.icalString,
       all_day:e.startDate.isDate,timezone:e.startDate.timezone.tzid,location:e.getProperty('LOCATION'),
       alarms:e.getAlarms().map(a=>a.offset?.inSeconds),sequence:e.getProperty('SEQUENCE')}))});
 }
 return {version:Services.appinfo.version,outcomes};
})().then(done).catch(e=>done({error:String(e)}));
"""


def make_files(root):
    app = Application(root / "calisift")
    try:
        wid = app.create_workspace("星辰奕歌")["id"]

        def change(operation):
            candidate = app.preview_change(
                wid, app.workspace(wid)["version"], operation
            )
            app.commit_change(candidate["preview_id"], candidate["base_version"])

        for value in [
            dict(
                date="2026-09-08",
                title="夜班，检查;路线\\备忘\n换行",
                start="20:00",
                end="08:00",
                end_date="2026-09-09",
                location="A,201",
            ),
            dict(date="2026-09-09", title="全天培训", all_day=True),
            dict(date="2027-01-05", title="期末考试", start="09:00"),
        ]:
            change(dict(type="manual", values=value))
        events = app.events(wid)["items"]
        paths = [root / (name + ".ics") for name in ("first", "changed", "removed")]
        app.export_file(wid, app.workspace(wid)["version"], dict(alarm=15), paths[0])
        value = {
            k: events[0][k]
            for k in ("date", "title", "start", "end", "end_date", "location")
        }
        value["start"] = "21:00"
        change(dict(type="edit", event_id=events[0]["id"], values=value))
        app.export_file(wid, app.workspace(wid)["version"], dict(alarm=15), paths[1])
        change(dict(type="hide", event_id=events[2]["id"]))
        app.export_file(wid, app.workspace(wid)["version"], dict(alarm=15), paths[2])
        return [str(p) for p in (paths[0], paths[0], paths[1], paths[2], paths[2])]
    finally:
        app.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="calisift-thunderbird-") as directory:
        root = Path(directory)
        paths = make_files(root)
        profile = root / "profile"
        profile.mkdir()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        preferences = {
            "marionette.port": port,
            "mail.provider.suppress_dialog_on_startup": True,
            "mail.shell.checkDefaultClient": False,
            "app.update.auto": False,
            "datareporting.policy.dataSubmissionEnabled": False,
            "toolkit.telemetry.enabled": False,
            "calendar.timezone.local": "Asia/Shanghai",
            "calendar.alarms.show": False,
        }
        (profile / "user.js").write_text(
            "\n".join(
                "user_pref(" + json.dumps(k) + "," + json.dumps(v) + ");"
                for k, v in preferences.items()
            ),
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [
                str(args.executable.resolve()),
                "-no-remote",
                "-profile",
                str(profile),
                "-marionette",
                "-remote-allow-system-access",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        client = None
        try:
            until = time.monotonic() + 35
            while time.monotonic() < until:
                try:
                    client = Marionette(port)
                    break
                except OSError:
                    time.sleep(0.2)
            if not client:
                raise RuntimeError("Thunderbird automation did not start")
            while time.monotonic() < until:
                if client.script(
                    "return typeof window.getItemsFromIcsFile==='function'"
                ):
                    break
                time.sleep(0.2)
            result = client.script(IMPORT_SCRIPT, [paths], True)
            assert "error" not in result, result
            first = result["outcomes"][0]
            assert first["count"] == 3 and not first["error_messages"]
            assert any(
                e["end"] == "20260909T080000" and e["alarms"] == [-900]
                for e in first["events"]
            )
            assert any(e["all_day"] and e["end"] == "20260910" for e in first["events"])
            assert any(
                e["start"] == e["end"] == "20270105T090000" for e in first["events"]
            )
            assert result["outcomes"][4]["count"] == 2
            assert any(
                e["start"] == "20260908T210000" for e in result["outcomes"][4]["events"]
            )
            result.update(
                system=platform.platform(),
                method="Real Thunderbird importer and local calendar storage via Marionette",
                native_file_picker_verified=False,
                alarm_delivery_verified=False,
            )
            output = Path("artifacts/thunderbird-ics.json")
            output.parent.mkdir(exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {k: v for k, v in result.items() if k != "outcomes"},
                    ensure_ascii=False,
                )
            )
            print("Event counts:", [r["count"] for r in result["outcomes"]])
        finally:
            if client:
                try:
                    client.send("Marionette:Quit", {"flags": ["eAttemptQuit"]})
                except (OSError, RuntimeError):
                    pass
                client.socket.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
