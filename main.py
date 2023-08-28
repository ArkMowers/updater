#!/usr/bin/env python3

import PySimpleGUI as sg
import platformdirs
import pathlib
import json
import requests
import htmllistparse
from hash import hash
from fnmatch import fnmatch


default_config = {
    "mirror": "https://mower.zhaozuohong.vip",
    "ignore": [
        "*.conf",
        "*.json",
        "tmp/**",
        "screenshot/**",
        "adb_buildin/**",
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
        sg.Text("点击“刷新”以获取版本列表", key="status", size=(71, 1)),
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
            continue
        result.append(
            {
                "version": v,
                "display_name": f"{v} ({pub_time})",
                "hash": r.json()["hash"],
            }
        )
    return result


new_list = []
replace_list = []
remove_list = []
ignore_list = []


def prepare_to_install(path, new_hash, pattern_list):
    global new_list
    global replace_list
    global remove_list
    global ignore_list
    new_list = []
    replace_list = []
    remove_list = []
    ignore_list = []
    for pattern in pattern_list:
        for file in path.glob(pattern):
            ignore_list.append(str(file)[len(str(path)) + 1 :])
    old_hash = hash(path)
    for f, h in new_hash.items():
        if f in old_hash:
            if old_hash[f] != h and f not in ignore_list:
                print(f)
                print(old_hash[f])
                print(h)
                replace_list.append(f)
        elif f not in ignore_list:
            new_list.append(f)
    for f, h in old_hash.items():
        if f not in new_hash and f not in ignore_list:
            remove_list.append(f)


version_name = ""


def download_single_file():
    mirror = conf["mirror"]
    if not mirror.endswith("/"):
        mirror += "/"
    global new_list
    global replace_list
    global remove_list
    if remove_list:
        subpath = remove_list.pop()
        path = pathlib.Path(conf["install_dir"]) / "mower" / subpath
        path.unlink()
        return subpath
    elif new_list:
        subpath = new_list.pop()
    elif replace_list:
        subpath = replace_list.pop()
    else:
        return None
    url = f"{mirror}{version_name}/{subpath}"
    print(url)
    r = requests.get(url)
    path = pathlib.Path(conf["install_dir"]) / "mower" / subpath
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open("wb") as f:
        f.write(r.content)
    return subpath


while True:
    event, values = window.read()
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
        window["status"].update("已获取版本列表")
    elif event == "开始安装":
        window["status"].update("正在安装……")
        version_display_name = values["versions"][0]
        version = next(i for i in versions if i["display_name"] == version_display_name)
        version_hash_list = version["hash"]
        version_name = version["version"]
        path = pathlib.Path(conf["install_dir"]) / "mower"
        path.mkdir(exist_ok=True, parents=True)
        window.perform_long_operation(
            lambda: prepare_to_install(path, version_hash_list, conf["ignore"]),
            "-calc-hash-",
        )
    elif event == "-calc-hash-":
        begin_install = sg.popup_scrolled(
            f"预计新增{len(new_list)}个文件：\n"
            + "\n".join(new_list)
            + f"\n\n替换{len(replace_list)}个文件：\n"
            + "\n".join(replace_list)
            + f"\n\n删除{len(remove_list)}个文件：\n"
            + "\n".join(remove_list)
            + "\n\n是否继续安装？",
            yes_no=True,
            title="安装确认",
        )
        if begin_install == "Yes":
            window.perform_long_operation(
                lambda: download_single_file(),
                "-install-single-",
            )
        else:
            window["status"].update("安装已取消")
    elif event == "-install-single-":
        subpath = values["-install-single-"]
        print(subpath)
        if subpath:
            window["status"].update(
                f"已处理{subpath}，剩余{len(remove_list) + len(replace_list) + len(new_list)}个文件……"
            )
            window.perform_long_operation(
                lambda: download_single_file(),
                "-install-single-",
            )
        else:
            window["status"].update("安装完成！")


window.close()

with conf_path.open("w") as f:
    json.dump(conf, f)
