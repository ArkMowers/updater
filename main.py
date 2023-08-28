#!/usr/bin/env python3

import PySimpleGUI as sg
import platformdirs
import pathlib
import json
import requests
import htmllistparse


default_config = {
    "mirror": "https://mower.zhaozuohong.vip",
    "ignore": [
        "*.conf",
        "*.json",
        "tmp/",
        "screenshot/",
        "adb_buildin/",
    ],
    "install_dir": "",
}

conf_dir_path = pathlib.Path(platformdirs.user_config_dir("mower_updater"))
conf_dir_path.mkdir(exist_ok=True, parents=True)
conf_path = conf_dir_path / "config.json"
if conf_path.exists():
    with conf_path.open("r") as f:
        conf = json.load(f)
        default_config.update(conf)
else:
    conf = default_config


layout = [
    [
        sg.Text("镜像：", size=(10, 1)),
        sg.Input(conf["mirror"], key="-mirror-", size=(53, 1)),
        sg.Button("刷新", size=(4, 1)),
    ],
    [
        sg.vtop(sg.Text("版本：", size=(10, 1))),
        sg.Listbox([], key="versions", size=(60, 6)),
    ],
    [
        sg.Text("安装目录：", size=(10, 1)),
        sg.Input(conf["install_dir"], size=(53, 1), key="install-dir"),
        sg.FolderBrowse("...", target="install-dir", size=(4, 1)),
    ],
    [
        sg.vtop(sg.Text("忽略：", size=(10, 1))),
        sg.Multiline("\n".join(conf["ignore"]), key="-ignore-", size=(60, 8)),
    ],
    [
        sg.Button("开始安装", size=(71, 2)),
    ],
    [
        sg.Text("", key="status", size=(71, 1)),
    ],
]

window = sg.Window(
    "arknights-mower updater",
    layout,
    enable_close_attempted_event=True,
)


def connect_mirror(mirror):
    try:
        cwd, listing = htmllistparse.fetch_listing(mirror, timeout=30)
        return {
            "status_code": 0,
            "versions": [v.name[:-1] for v in listing if v.name.endswith("/")],
        }
    except Exception as e:
        return {
            "status_code": -1,
            "msg": str(e),
        }


def fetch_version_details(mirror, versions):
    if not mirror.endswith("/"):
        mirror += "/"
    result = []
    for v in versions:
        url = mirror + v + "/version.json"
        try:
            r = requests.get(url)
            pub_time = r.json()["time"]
        except Exception as e:
            print(e)
            continue
        result.append(
            {
                "version": v,
                "display_name": f"{v} ({pub_time})",
            }
        )
    return result


while True:
    event, values = window.read()
    print(event)
    print(values)

    conf["mirror"] = values["-mirror-"]
    conf["ignore"] = [l for l in values["-ignore-"].splitlines() if l.strip()]
    conf["install_dir"] = values["install-dir"]
    if event == sg.WINDOW_CLOSE_ATTEMPTED_EVENT:
        break
    elif event == "刷新":
        window["status"].update("正在连接镜像……")
        window.perform_long_operation(
            lambda: connect_mirror(conf["mirror"]),
            "-connect-mirror-",
        )
    elif event == "-connect-mirror-":
        status_code = values["-connect-mirror-"]["status_code"]
        if status_code == 0:
            window["status"].update("正在从镜像获取版本……")
            links = values["-connect-mirror-"]["versions"]
            window.perform_long_operation(
                lambda: fetch_version_details(conf["mirror"], links),
                "-version-details-",
            )
        else:
            sg.PopupError(values["-connect-mirror-"]["msg"])
    elif event == "-version-details-":
        versions = values["-version-details-"]
        window["versions"].update(values=[v["display_name"] for v in versions])
        window["status"].update("")
    elif event == "开始安装":
        print("install")

window.close()

print(conf)
with conf_path.open("w") as f:
    json.dump(conf, f)
