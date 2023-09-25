import PySimpleGUI as sg
import pathlib
from utils import remove_tail_slash
from updater import Updater

updater = Updater()
updater._load_conf()
conf = updater.conf
version_name = ""
diff = None
install_path = None
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
        sg.Multiline("\n".join(conf["ignores"]), key="-ignore-", size=(60, 8)),
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

def download_progress_callback(remains: int, subpath: str):
    window['status'].update(f"已处理{subpath}，剩余{remains}个文件……")
def download_guard():
    try:
        updater.download_all_files(version_name, diff, download_progress_callback)
    except Exception as e:
        window["status"].update('下载失败: {}'.format(str(e)))
        raise e

while True:
    event, values = window.read()
    conf["mirror"] = remove_tail_slash(values["-mirror-"])
    conf["ignore"] = [l for l in values["-ignore-"].splitlines() if l.strip()]
    conf["install_dir"] = values["install-dir"]
    conf["dir_name"] = values["dir-name"]
    conf["pool_limit"] = int(values["pool-limit"])
    install_path = pathlib.Path(conf["install_dir"]) / conf["dir_name"]
    if event == sg.WINDOW_CLOSE_ATTEMPTED_EVENT:
        break
    elif event == "刷新":
        window["status"].update("正在连接镜像……")
        window.perform_long_operation(
            lambda: updater.connect_mirror(),
            "-connect-mirror-",
        )
    elif event == "-connect-mirror-":
        status_code = values["-connect-mirror-"]["status_code"]
        if status_code == 0:
            window["status"].update("正在从镜像获取版本……")
            links = values["-connect-mirror-"]["versions"]
            window.perform_long_operation(
                lambda: updater.fetch_version_details(links),
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
        window.perform_long_operation(
            lambda: updater.get_diff(install_path, version_hash_list),
            "-calc-hash-",
        )
    elif event == "-calc-hash-":
        diff = values["-calc-hash-"]
        begin_install = sg.popup_scrolled(
            f"arknights-mower 将安装至{pathlib.Path(conf['install_dir']) / conf['dir_name']}"
            + f"\n\n预计删除{len(diff.remove_list)}个文件：\n"
            + "\n".join(diff.remove_list)
            + f"\n\n新增{len(diff.new_list)}个文件：\n"
            + "\n".join(diff.new_list)
            + f"\n\n替换{len(diff.replace_list)}个文件：\n"
            + "\n".join(diff.replace_list)
            + "\n\n是否继续安装？",
            yes_no=True,
            size=(80, 24),
            title="安装确认",
        )
        if begin_install == "Yes":
            window.perform_long_operation(
                lambda: updater.install(version_name, install_path),
                "-download-finish-",
            )
        else:
            window["status"].update("安装已取消")
    elif event == "-download-finish-":
        # updater.perform_install(version_name, install_path, diff)
        window["status"].update("安装完成！")


window.close()
updater._save_conf() # ensure saved
