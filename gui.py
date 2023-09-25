#!/usr/bin/env python3

import PySimpleGUI as sg
import platformdirs
import pathlib
import json
import requests
import htmllistparse
from utils import hash
from multiprocessing.pool import ThreadPool
from multiprocessing.queues import Queue

default_config = {
    "mirror": "https://mower.zhaozuohong.vip",
    "code": [
        "arknights_mower/__init__/data/**/*",
        "arknights_mower/__init__/solvers/**/*",
        "arknights_mower/__init__/templates/**/*",
        "arknights_mower/__init__/ocr/**/*"
    ],
    "code_tips": [
        "code列表中的内容是所有经常变更的内容，具有较强的时效性",
        "code列表的内容会在发布时打包为zip，以减少传输量，保证版本变更一致性"
    ],
    "resources": [
        "当前版本这是一个无效的参数",
        "因为既不在ignores也不在code中的文件自动成为resources"
    ],
    "resources_tips": [
        "resources列表的内容会在发布时与上个版本进行差异比较"
    ],
    "ignores": [
        "*.yml",
        "*.json",
        "tmp/*",
        "log/*",
        "screenshot/**/*",
        "adb-buildin/*"
    ],
    "install_dir": "",
    "pool_limit": 32,
    "dir_name": "mower"
}

conf_dir_path = pathlib.Path(platformdirs.user_config_dir("mower_updater"))
tmp_path = pathlib.Path(platformdirs.user_cache_dir("mower_updater"))
conf_dir_path.mkdir(exist_ok=True, parents=True)
conf_path = conf_dir_path / "config.json"
if conf_path.exists():
    with conf_path.open("r") as f:
        conf = json.load(f)
        default_config.update(conf)
conf = default_config


layout = [
    [
        sg.Text("镜像：", size=(10, 1)),
        sg.Input(conf["mirror"], key="-mirror-", size=(55, 1)),
        sg.Button("刷新", size=(4, 1)),
    ],
    [
        sg.vtop(sg.Text("版本：", size=(10, 1))),
        sg.Listbox([], key="versions", size=(60, 6)),
    ],
    [
        sg.Text("安装位置：", size=(10, 1)),
        sg.Input(conf["install_dir"], size=(55, 1), key="install-dir"),
        sg.FolderBrowse("...", target="install-dir", size=(4, 1)),
    ],
    [
        sg.Text("子文件夹：", size=(10, 1)),
        sg.Input(conf["dir_name"], size=(62, 1), key="dir-name"),
    ],
    [
        sg.vtop(sg.Text("忽略：", size=(10, 1))),
        sg.Multiline("\n".join(conf["ignore"]), key="-ignore-", size=(60, 8)),
    ],
    [
        sg.Text("线程数：", size=(10, 1)),
        sg.Input(conf["pool_limit"], size=(62, 1), key="pool-limit"),
    ],
    [
        sg.Button("开始安装", size=(66, 2)),
    ],
    [
        sg.Text("点击“刷新”以获取版本列表", key="status", size=(66, 1)),
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
            ignore_list.append(str(file)[len(str(path)) + 1 :].replace("\\", "/"))
    old_hash = hash(path)
    for f, h in new_hash.items():
        if f in old_hash:
            if old_hash[f] != h and f not in ignore_list:
                replace_list.append(f)
        elif f not in ignore_list:
            new_list.append(f)
    for f, h in old_hash.items():
        if f not in new_hash and f not in ignore_list:
            remove_list.append(f)


version_name = ""

failed_list = []
session_pool = Queue()

def remove_files():
    global remove_list
    global failed_list
    for subpath in remove_list:
        path = pathlib.Path(conf["install_dir"]) / conf["dir_name"] / subpath
        try:
            path.unlink()
        except Exception as e:
            failed_list.append({"path": path, "reason": str(e)})
    remove_list = []


def download_single_file(subpath):
    global failed_list
    mirror = conf["mirror"]
    if not mirror.endswith("/"):
        mirror += "/"
    url = f"{mirror}{version_name}/{subpath}"
    try:
        r = requests.get(url)
        path = pathlib.Path(conf["install_dir"]) / conf["dir_name"] / subpath
        path.parent.mkdir(exist_ok=True, parents=True)
        with path.open("wb") as f:
            f.write(r.content)
    except Exception as e:
        failed_list.append({"path": path, "reason": str(e)})
    return subpath


def download_all_files(window):
    remove_files()
    remain_files = len(new_list) + len(replace_list)
    with ThreadPool(conf["pool_limit"]) as pool:
        for subpath in pool.imap_unordered(
            download_single_file, new_list + replace_list
        ):
            remain_files -= 1
            window["status"].update(f"已处理{subpath}，剩余{remain_files}个文件……")


while True:
    event, values = window.read()
    conf["mirror"] = values["-mirror-"]
    conf["ignore"] = [l for l in values["-ignore-"].splitlines() if l.strip()]
    conf["install_dir"] = values["install-dir"]
    conf["dir_name"] = values["dir-name"]
    conf["pool_limit"] = int(values["pool-limit"])
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
        failed_list = []
        if not conf["dir_name"]:
            sg.popup_error("子文件夹不可为空！")
            continue
        if not values["versions"]:
            window["status"].update("请选择要安装的版本！")
            continue
        window["status"].update("开始安装……")
        version_display_name = values["versions"][0]
        version = next(i for i in versions if i["display_name"] == version_display_name)
        version_hash_list = version["hash"]
        version_name = version["version"]
        path = pathlib.Path(conf["install_dir"]) / conf["dir_name"]
        path.mkdir(exist_ok=True, parents=True)
        window.perform_long_operation(
            lambda: prepare_to_install(path, version_hash_list, conf["ignore"]),
            "-calc-hash-",
        )
    elif event == "-calc-hash-":
        begin_install = sg.popup_scrolled(
            f"arknights-mower 将安装至{pathlib.Path(conf['install_dir']) / conf['dir_name']}"
            + f"\n\n预计删除{len(remove_list)}个文件：\n"
            + "\n".join(remove_list)
            + f"\n\n新增{len(new_list)}个文件：\n"
            + "\n".join(new_list)
            + f"\n\n替换{len(replace_list)}个文件：\n"
            + "\n".join(replace_list)
            + "\n\n是否继续安装？",
            yes_no=True,
            size=(80, 24),
            title="安装确认",
        )
        if begin_install == "Yes":
            window.perform_long_operation(
                lambda: download_all_files(window),
                "-download-finish-",
            )
        else:
            window["status"].update("安装已取消")
    elif event == "-download-finish-":
        if failed_list:
            window["status"].update("安装失败！")
            sg.popup_scrolled(
                "\n".join([f"{i['path']}: {i['reason']}" for i in failed_list]),
                yes_no=True,
                size=(80, 24),
                title="安装失败",
            )
        else:
            window["status"].update("安装完成！")


window.close()

with conf_path.open("w") as f:
    json.dump(conf, f)
